import { Suspense } from "react";

import { Landing } from "@/components/landing/landing";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { localeOf, pageMetadata, serverT } from "@/i18n/server";

export async function generateMetadata({ params }: PageProps<"/[locale]">) {
  const locale = await localeOf(params);
  const t = serverT(locale, "landing");
  return pageMetadata(locale, "/", t("metaTitle"), t("metaDescription"));
}

async function LandingFor({ params }: { params: PageProps<"/[locale]">["params"] }) {
  return <Landing locale={await localeOf(params)} />;
}

// The language comes from the URL, read inside <Suspense> (Next's instant-navigation rule). Both languages are
// prerendered (generateStaticParams in the layout), so the static HTML already holds the content, not the fallback.
export default function Home({ params }: PageProps<"/[locale]">) {
  return (
    <>
      <SiteHeader />
      <main className="flex-1 bg-grid pb-12">
        <Suspense fallback={null}>
          <LandingFor params={params} />
        </Suspense>
      </main>
      <SiteFooter />
    </>
  );
}
