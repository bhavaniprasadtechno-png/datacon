import { Body, Controller, Delete, Get, Logger, Param, Patch, Post, Query, Res, UseGuards } from "@nestjs/common";
import type { Response } from "express";
import { JwtAuthGuard } from "../auth/guards/jwt-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { AiClientService } from "../common/ai-client.service";
import { MetricsService } from "../metrics/metrics.service";
import { ChatService } from "./chat.service";
import { SendMessageDto } from "./dto/send-message.dto";
import { FeedbackDto } from "./dto/feedback.dto";

const DEFAULT_MODEL = "Holt-Winters";
const DEFAULT_HORIZON = 6;

@UseGuards(JwtAuthGuard, PermissionsGuard)
@Controller("chat")
export class ChatController {
  private readonly logger = new Logger(ChatController.name);

  constructor(
    private readonly chat: ChatService,
    private readonly metrics: MetricsService,
    private readonly ai: AiClientService,
  ) {}

  @Get("conversations")
  async conversations(@CurrentUser() user: AuthenticatedUser) {
    return this.chat.listConversations(user.id);
  }

  @Post("conversations")
  async createConversation(@CurrentUser() user: AuthenticatedUser) {
    return this.chat.createConversation(user.id);
  }

  @Delete("conversations/:id")
  async deleteConversation(@Param("id") id: string, @CurrentUser() user: AuthenticatedUser) {
    await this.chat.deleteConversation(user.id, id);
    return { ok: true };
  }

  @Get("messages")
  async messages(@Query("conversationId") conversationId: string | undefined, @CurrentUser() user: AuthenticatedUser) {
    return this.chat.listMessages(user.id, conversationId);
  }

  @RequirePermissions("ask_agents")
  @Post("stream")
  async stream(@Body() dto: SendMessageDto, @CurrentUser() user: AuthenticatedUser, @Res() res: Response) {
    const conversation = await this.chat.getOrCreateConversation(user.id, dto.conversationId);
    await this.chat.appendUserMessage(conversation.id, dto.message);
    const context = await this.metrics.chatContext(DEFAULT_MODEL, DEFAULT_HORIZON);

    let upstream;
    try {
      upstream = await this.ai.client.post(
        "/internal/chat/stream",
        { message: dto.message, context, model: dto.model },
        { responseType: "stream" },
      );
    } catch (e: unknown) {
      // Respond as a clean JSON error *before* touching any SSE headers —
      // if we set them first and this call throws, Nest's exception filter
      // can't cleanly override an already-started response, and the client
      // gets a generic "Internal server error" with no useful detail.
      this.logger.error(`AI service call failed for chat stream: ${e instanceof Error ? e.message : e}`);
      res.status(502).json({
        message: "The AI service is temporarily unavailable — please try again in a moment.",
      });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    // Sent first so the client always knows which conversation this reply
    // landed in — matters when it didn't pass a conversationId itself (e.g.
    // very first message ever) and the server picked/created one.
    res.write(`event: conversation\ndata: ${JSON.stringify({ conversationId: conversation.id })}\n\n`);

    let buffer = "";
    let finalIntent = "descriptive";
    let finalText = "";
    let finalPayload: unknown = null;

    upstream.data.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      buffer += text;
      res.write(chunk);

      const doneMatch = buffer.match(/event: done\ndata: (.+)\n\n/);
      if (doneMatch) {
        try {
          const parsed = JSON.parse(doneMatch[1]);
          finalIntent = parsed.intent;
          finalText = parsed.text;
          finalPayload = parsed.payload;
        } catch {
          // ignore parse errors — the client already has the raw event either way
        }
      }
    });

    upstream.data.on("end", async () => {
      if (finalText) {
        await this.chat.appendAgentMessage(conversation.id, finalIntent, finalText, finalPayload);
      }
      res.end();
    });

    upstream.data.on("error", () => res.end());
  }

  @Patch("messages/:id/feedback")
  async feedback(@Param("id") id: string, @Body() dto: FeedbackDto, @CurrentUser() user: AuthenticatedUser) {
    return this.chat.setFeedback(id, user.id, dto.vote);
  }
}
