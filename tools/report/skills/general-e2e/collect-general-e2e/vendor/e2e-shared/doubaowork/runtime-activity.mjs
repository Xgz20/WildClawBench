export async function readNativeActivity(page) {
  return page.evaluate(() => {
    const chunks = window["@flow-web/desktop:stable"];
    if (!Array.isArray(chunks)) throw new Error("DOUBAOWORK_ACTIVITY_PROFILE_UNAVAILABLE");
    let require;
    const item = [[`wcb-activity-${crypto.randomUUID()}`], {}, r => { require = r; }];
    chunks.push(item); if (chunks.at(-1) === item) chunks.pop();
    if (!String(require?.m?.[37476] || "").includes("Resource controller of GLOBAL_STORE not found")) throw new Error("DOUBAOWORK_ACTIVITY_PROFILE_UNSUPPORTED");
    const module = require(37476);
    const containers = [module.XQ(), module.ne()];
    const services = [...new Set(containers.filter(c => c.serviceContainer.isBound("chatIMService")).map(c => c.serviceContainer.get("chatIMService")))];
    const rows = [];
    for (const service of services) {
      const tasks = service.getTaskService(), values = Object.values(tasks.mainTaskService.tasks);
      if (values.length > 32) throw new Error("DOUBAOWORK_ACTIVITY_LIMIT");
      for (const task of values) {
        const data = tasks.checkpointService.getMainTaskData(task.sessionId);
        const ids = Object.values(data?.sentMessages || {}).flatMap(m => [m.extra?.conversation_id, m.extra?.local_conversation_id])
          .filter(id => typeof id === "string" && /^[0-9]{1,64}$/u.test(id) && id !== "0");
        rows.push({ session_id: task.sessionId, conversation_ids: [...new Set(ids)] });
      }
    }
    return { source: "chatIMService.mainTaskService.tasks+checkpoint.sentMessages", initialized: services.length > 0, active: rows };
  });
}

export function assertNativeActivityAllowed(activity, conversationIds = [], sessionIds = []) {
  if (activity?.initialized !== true || !Array.isArray(activity.active)) throw new Error("DOUBAOWORK_ACTIVITY_UNVERIFIED");
  const conversations = new Set(conversationIds), sessions = new Set(sessionIds);
  for (const task of activity.active) {
    if (sessions.has(task.session_id)) continue;
    if (!task.conversation_ids?.length || !task.conversation_ids.every(id => conversations.has(id))) throw new Error("DOUBAOWORK_UNREGISTERED_NATIVE_ACTIVITY");
  }
}
