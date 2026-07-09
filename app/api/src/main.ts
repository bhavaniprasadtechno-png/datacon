import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { ValidationPipe } from "@nestjs/common";
import { NestExpressApplication } from "@nestjs/platform-express";
import cookieParser from "cookie-parser";
import { join } from "path";
import { AppModule } from "./app.module";

async function bootstrap() {
  const app = await NestFactory.create<NestExpressApplication>(AppModule);
  app.use(cookieParser());
  app.enableCors({
    origin: (process.env.CORS_ORIGINS ?? "http://localhost:5173").split(","),
    credentials: true,
  });
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  app.setGlobalPrefix("api");

  // Serve the built Vite frontend as static files
  const webDistPath = join(__dirname, "..", "..", "web", "dist");
  app.useStaticAssets(webDistPath, { prefix: "/" });

  // SPA fallback: serve index.html for all non-API routes
  app.use(
    (
      req: { path: string },
      res: { sendFile: (path: string) => void },
      next: () => void,
    ) => {
      if (
        !req.path.startsWith("/api") &&
        !req.path.startsWith("/health")
      ) {
        res.sendFile(join(webDistPath, "index.html"));
      } else {
        next();
      }
    },
  );

  const port = process.env.PORT ? Number(process.env.PORT) : 4000;
  await app.listen(port);
  // eslint-disable-next-line no-console
  console.log(`Datacon API listening on http://localhost:${port}/api`);
}
bootstrap();
