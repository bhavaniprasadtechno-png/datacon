import { Card, CardContent } from "../../components/shadcn-ui/ui/card";

export function ComingSoonPage({ title }: { title: string }) {
  return (
    <div className="mx-auto max-w-[1080px] p-8">
      <h1 className="text-xl font-extrabold">{title}</h1>
      <Card className="mt-10">
        <CardContent className="py-10 text-center text-[13.5px] text-[#9499ad]">
          {title} isn't built yet — coming in a future update.
        </CardContent>
      </Card>
    </div>
  );
}
