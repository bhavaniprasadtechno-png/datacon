CREATE TYPE "AccountStatus" AS ENUM ('ACTIVE', 'SUSPENDED');

ALTER TABLE "organizations" ADD COLUMN "status" "AccountStatus" NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE "users" ADD COLUMN "status" "AccountStatus" NOT NULL DEFAULT 'ACTIVE';
