import { Body, Controller, Delete, Get, Logger, Param, Patch, Post, Query, Res, UseGuards } from "@nestjs/common";
import type { Response } from "express";
import { JwtAuthGuard } from "../auth/guards/jwt-auth.guard";
import { PermissionsGuard } from "../auth/guards/permissions.guard";
import { RequirePermissions } from "../auth/decorators/require-permissions.decorator";
import { CurrentUser } from "../auth/decorators/current-user.decorator";
import { AuthenticatedUser } from "../auth/token.types";
import { AiClientService } from "../common/ai-client.service";
import { ChatService } from "./chat.service";
import { SendMessageDto } from "./dto/send-message.dto";
import { FeedbackDto } from "./dto/feedback.dto";

@UseGuards(JwtAuthGuard, PermissionsGuard)
@Controller("chat")
export class ChatController {
  private readonly logger = new Logger(ChatController.name);

  constructor(
    private readonly chat: ChatService,
    private readonly ai: AiClientService,
  ) {}

  @Get("conversations")
  async conversations(@Query("search") search: string | undefined, @CurrentUser() user: AuthenticatedUser) {
    return this.chat.listConversations(user.id, search);
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
    this.logger.log(`[Chat] Received chat request from user ${user.id} (ConversationId: "${dto.conversationId ?? 'NEW'}")`);
    
    const conversation = await this.chat.getOrCreateConversation(user.id, dto.conversationId);
    this.logger.log(`[Chat] Using Conversation ID: ${conversation.id}. Appending user message: "${dto.message}"`);
    await this.chat.appendUserMessage(conversation.id, dto.message);

    let upstream;
    try {
      this.logger.log(`[Chat] Posting chat stream request to AI Service...`);
      upstream = await this.ai.client.post(
        "/internal/chat/stream",
        { message: dto.message, model: dto.model },
        { responseType: "stream" },
      );
      this.logger.log(`[Chat] AI Service responded with stream status: ${upstream.status}`);
    } catch (e: unknown) {
      // Respond as a clean JSON error *before* touching any SSE headers —
      // if we set them first and this call throws, Nest's exception filter
      // can't cleanly override an already-started response, and the client
      // gets a generic "Internal server error" with no useful detail.
      this.logger.error(`[Chat] AI service call failed for chat stream: ${e instanceof Error ? e.message : e}`);
      res.status(502).json({
        message: "The AI service is temporarily unavailable — please try again in a moment.",
      });
      return;
    }

    this.logger.log(`[Chat] Initializing Server-Sent Events (SSE) stream headers...`);
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    // Sent first so the client always knows which conversation this reply
    // landed in — matters when it didn't pass a conversationId itself (e.g.
    // very first message ever) and the server picked/created one.
    res.write(`event: conversation\ndata: ${JSON.stringify({ conversationId: conversation.id })}\n\n`);

    // Pass the raw stream through untouched while incrementally parsing SSE
    // frames on the side, collecting each agent's finished result — one
    // question can now fan out to several agents (SRS Fig. 2's per-agent
    // loop), so there are multiple agent_done frames to persist, one
    // Message row each.
    let buffer = "";
    const results: { intent: string; text: string; payload: unknown }[] = [];

    upstream.data.on("data", (chunk: Buffer) => {
      res.write(chunk);
      buffer += chunk.toString("utf8");

      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const eventMatch = frame.match(/^event: (.+)$/m);
        const dataMatch = frame.match(/^data: (.+)$/m);
        
        if (eventMatch) {
          const eventType = eventMatch[1];
          if (eventType === "agent_start" && dataMatch) {
            try {
              const startData = JSON.parse(dataMatch[1]);
              this.logger.log(`[Chat] [Conversation ${conversation.id}] Agent '${startData.intent}' has started responding.`);
            } catch {}
          } else if (eventType === "agent_done" && dataMatch) {
            try {
              const doneData = JSON.parse(dataMatch[1]);
              this.logger.log(`[Chat] [Conversation ${conversation.id}] Agent '${doneData.intent}' finished response. Text length: ${doneData.text?.length ?? 0}`);
              results.push(doneData);
            } catch (err) {
              this.logger.warn(`[Chat] Failed to parse agent_done event data: ${err}`);
            }
          }
        }
      }
    });

    upstream.data.on("end", async () => {
      this.logger.log(`[Chat] [Conversation ${conversation.id}] AI Service stream closed. Persisting ${results.length} agent response(s) to DB...`);
      for (const result of results) {
        if (result.text) {
          this.logger.log(`[Chat] [Conversation ${conversation.id}] Saving response for agent '${result.intent}' to Postgres...`);
          await this.chat.appendAgentMessage(conversation.id, result.intent, result.text, result.payload);
        }
      }
      this.logger.log(`[Chat] [Conversation ${conversation.id}] End response stream successfully.`);
      res.end();
    });

    upstream.data.on("error", (err: any) => {
      this.logger.error(`[Chat] [Conversation ${conversation.id}] Error in upstream AI stream: ${err?.message ?? err}`);
      res.end();
    });
  }

  @Patch("messages/:id/feedback")
  async feedback(@Param("id") id: string, @Body() dto: FeedbackDto, @CurrentUser() user: AuthenticatedUser) {
    return this.chat.setFeedback(id, user.id, dto.vote);
  }
}
