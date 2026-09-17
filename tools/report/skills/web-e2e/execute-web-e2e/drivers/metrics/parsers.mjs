// Web adapter: preserve the published Web metric schema while the parsing
// mechanism comes from the versioned scenario-neutral component.
import {
  TOKEN_KEYS,
  createNativeResourceMetricParsers,
} from "../../vendor/e2e-shared/resource-metrics/native-parsers.mjs";
import { verifiedQwenProfile } from "./qwen-profile.mjs";

export const VERSION = "1.1.3";
export { TOKEN_KEYS };

const parsers = createNativeResourceMetricParsers({
  schemaVersion: "wildclawbench.web-e2e-resource-collection/v1",
  version: VERSION,
  scope: "primary-task",
  excludedScope: [
    "unobserved-http-retries",
    "unlinked-child-agents",
    "client-background-services",
  ],
  resolveQwenProfile: verifiedQwenProfile,
});

export const {
  count,
  elapsed,
  empty,
  setMetric,
  parseWorkBuddy,
  parseAstron,
  parseQwen,
} = parsers;
