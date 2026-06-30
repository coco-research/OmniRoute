import { registerProviders } from "./providers.mjs";
import { registerProvider } from "./provider-cmd.mjs";
import { registerKeys } from "./keys.mjs";
import { registerModels } from "./models.mjs";
import { registerCombo } from "./combo.mjs";
import { registerLaunch } from "./launch.mjs";
import { registerSetupClaude } from "./setup-claude.mjs";
import { registerHealth } from "./health.mjs";
import { registerStatus } from "./status.mjs";
import { registerServe } from "./serve.mjs";
import { registerStop } from "./stop.mjs";
import { registerRestart } from "./restart.mjs";
import { registerEnv } from "./env.mjs";
import { registerTestProvider } from "./test-provider.mjs";
import { registerConfig } from "./config.mjs";
import { registerApiCommands } from "../api-commands/registry.mjs";

export function registerCommands(program) {
  registerProviders(program);
  registerProvider(program);
  registerKeys(program);
  registerModels(program);
  registerCombo(program);
  registerLaunch(program);
  registerSetupClaude(program);
  registerHealth(program);
  registerStatus(program);
  registerServe(program);
  registerStop(program);
  registerRestart(program);
  registerEnv(program);
  registerTestProvider(program);
  registerConfig(program);
  registerApiCommands(program);
}
