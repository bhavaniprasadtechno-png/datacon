import { CallHandler, ExecutionContext, Injectable, NestInterceptor } from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { Observable } from "rxjs";
import { orgContextStorage } from "./org-context.storage";
import { BOOTSTRAPPING_KEY } from "../auth/decorators/bootstrapping.decorator";

@Injectable()
export class OrgContextInterceptor implements NestInterceptor {
  constructor(private readonly reflector: Reflector) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const req = context.switchToHttp().getRequest();
    const isBootstrapping = this.reflector.getAllAndOverride<boolean>(BOOTSTRAPPING_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);

    const ctx = req.platformAdmin || isBootstrapping
      ? { isPlatformAdmin: true }
      : req.user
        ? { orgId: req.user.orgId }
        : {};

    return new Observable((subscriber) => {
      orgContextStorage.run(ctx, () => {
        next.handle().subscribe(subscriber);
      });
    });
  }
}
