-- AlterTable
ALTER TABLE "data_sources" ADD COLUMN     "columns" JSONB,
ADD COLUMN     "sampleRows" JSONB;
