import { Injectable, NotFoundException } from "@nestjs/common";
import { Intent } from "@datacon/prisma";
import { PrismaService } from "../prisma/prisma.service";

const INTENT_MAP: Record<string, Intent> = {
  descriptive: "DESCRIPTIVE",
  diagnostic: "DIAGNOSTIC",
  predictive: "PREDICTIVE",
  prescriptive: "PRESCRIPTIVE",
};

@Injectable()
export class ChatService {
  constructor(private readonly prisma: PrismaService) {}

  /** Resolves the conversation for a request: an explicit id (verified to belong
   * to the user), else the user's most recently active conversation, else a
   * freshly created one. Used both by the stream endpoint (conversationId
   * optional — old clients / a first-ever visit still work) and listMessages. */
  async getOrCreateConversation(userId: string, conversationId?: string) {
    if (conversationId) {
      const existing = await this.prisma.conversation.findFirst({ where: { id: conversationId, userId } });
      if (!existing) throw new NotFoundException("Conversation not found.");
      return existing;
    }
    const latest = await this.prisma.conversation.findFirst({ where: { userId }, orderBy: { updatedAt: "desc" } });
    if (latest) return latest;
    return this.prisma.conversation.create({ data: { userId, title: "New chat" } });
  }

  async createConversation(userId: string) {
    return this.prisma.conversation.create({ data: { userId, title: "New chat" } });
  }

  async listConversations(userId: string, search?: string) {
    const term = search?.trim();
    // Claude-style search: match the title OR any message's text (both
    // case-insensitive), so a query finds conversations by what was said in
    // them, not just what they were auto-titled. "messages: { some: {} }"
    // hides conversations nothing has been sent in yet (e.g. a freshly
    // created "New chat" the user hasn't typed into), so the list only
    // ever shows chats that actually happened.
    const where = term
      ? {
          userId,
          messages: { some: {} },
          OR: [
            { title: { contains: term, mode: "insensitive" as const } },
            { messages: { some: { text: { contains: term, mode: "insensitive" as const } } } },
          ],
        }
      : { userId, messages: { some: {} } };
    const conversations = await this.prisma.conversation.findMany({
      where,
      orderBy: { updatedAt: "desc" },
      include: { messages: { orderBy: { createdAt: "desc" }, take: 1, select: { text: true } } },
    });
    return conversations.map((c) => ({
      id: c.id,
      title: c.title ?? "New chat",
      updatedAt: c.updatedAt,
      preview: c.messages[0]?.text ?? null,
    }));
  }

  async deleteConversation(userId: string, conversationId: string) {
    const existing = await this.prisma.conversation.findFirst({ where: { id: conversationId, userId } });
    if (!existing) throw new NotFoundException("Conversation not found.");
    await this.prisma.conversation.delete({ where: { id: conversationId } });
  }

  async listMessages(userId: string, conversationId?: string) {
    const conversation = await this.getOrCreateConversation(userId, conversationId);
    const messages = await this.prisma.message.findMany({
      where: { conversationId: conversation.id },
      orderBy: { createdAt: "asc" },
      include: { feedback: true },
    });
    return {
      conversationId: conversation.id,
      messages: messages.map((m) => ({
        id: m.id,
        role: m.role,
        intent: m.intent?.toLowerCase() ?? null,
        text: m.text,
        payload: m.payload,
        vote: m.feedback?.vote ?? 0,
        createdAt: m.createdAt,
      })),
    };
  }

  async appendUserMessage(conversationId: string, text: string) {
    const message = await this.prisma.message.create({ data: { conversationId, role: "user", text } });
    // Auto-title from the first message, ChatGPT-style, and bump updatedAt so
    // "recent chats" ordering reflects actual activity — verified Prisma does
    // NOT bump @updatedAt on an update() call with an empty data: {}, so it
    // must be set explicitly here rather than relying on the field default.
    const messageCount = await this.prisma.message.count({ where: { conversationId } });
    await this.prisma.conversation.update({
      where: { id: conversationId },
      data: { updatedAt: new Date(), ...(messageCount === 1 ? { title: text.slice(0, 60) } : {}) },
    });
    return message;
  }

  async appendAgentMessage(conversationId: string, intent: string, text: string, payload: unknown) {
    const message = await this.prisma.message.create({
      data: { conversationId, role: "agent", intent: INTENT_MAP[intent], text, payload: payload as any },
    });
    await this.prisma.conversation.update({ where: { id: conversationId }, data: { updatedAt: new Date() } });
    return message;
  }

  async setFeedback(messageId: string, userId: string, vote: -1 | 0 | 1) {
    const message = await this.prisma.message.findUnique({ where: { id: messageId } });
    if (!message) throw new NotFoundException("Message not found.");
    if (vote === 0) {
      await this.prisma.feedback.deleteMany({ where: { messageId } });
      return { vote: 0 };
    }
    await this.prisma.feedback.upsert({
      where: { messageId },
      update: { vote, userId },
      create: { messageId, userId, vote },
    });
    return { vote };
  }
}
