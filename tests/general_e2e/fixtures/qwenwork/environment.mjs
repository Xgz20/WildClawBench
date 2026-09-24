export const gui = () => ({ schema: 'wildclawbench.macos-gui-session/v1', observed_at: new Date().toISOString(),
  screen_locked: false, console_session_verified: true, unlocked: true, error: null });
export const environment = () => ({ schema: 'wildclawbench.qwenwork-execution-environment/v1',
  app_path: '/Applications/QwenWorkCN.app', endpoint: 'http://127.0.0.1:9250', gui: gui(),
  listener: { pid: 12345, process_start_identity: 'fixture-start', command_sha256: 'a'.repeat(64), token_usage_exposed: true },
  cdp: { ready: true, websocket_verified: true, browser_identity_present: true }, verified: true, error: null });
