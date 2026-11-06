// next-intl's request configuration (required by its plugin). The site reads no request data: pages get their
// locale from the URL and pass messages explicitly (i18n/server.ts, i18n/localized.tsx), so this only names the
// default for any server API called without a locale.
import { getRequestConfig } from "next-intl/server";

import { DEFAULT_LOCALE, TIME_ZONE } from "./config";

export default getRequestConfig(async () => ({ locale: DEFAULT_LOCALE, timeZone: TIME_ZONE }));
