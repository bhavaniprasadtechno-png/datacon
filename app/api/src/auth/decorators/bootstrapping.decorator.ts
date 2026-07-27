import { SetMetadata } from "@nestjs/common";

export const BOOTSTRAPPING_KEY = "isBootstrapping";
export const Bootstrapping = () => SetMetadata(BOOTSTRAPPING_KEY, true);
