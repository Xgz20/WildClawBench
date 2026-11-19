import { execFile } from "node:child_process";
import { freemem, loadavg, totalmem } from "node:os";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { nativeInfrastructureRole, parseDarwinProcessTable }
  from "../../vendor/e2e-shared/task-process-cleanup/macos-task-processes.mjs";
import { evidenceClock } from "./astronstudio-evidence-files.mjs";

const run = promisify(execFile);
const counters = fileURLToPath(new URL("./astronstudio-rusage.py", import.meta.url));
const options = { timeout: 1_500, maxBuffer: 2 * 1024 * 1024, env: { LC_ALL: "C", LANG: "C" } };

async function probe(name, args) {
  try {
    return { value: (await run(name, args, options)).stdout.trim() };
  } catch (error) {
    return { unavailable: String(error.code || error.name) };
  }
}

export async function hostBootId() {
  if (process.platform !== "darwin") return null;
  return (await probe("/usr/sbin/sysctl", ["-n", "kern.bootsessionuuid"])).value ?? null;
}

export async function sampleNativeHost(appPath, previouslyTracked = []) {
  const start = evidenceClock();
  const result = {
    ...start, processes: [], observations_unavailable: [],
    host: { physical_bytes: totalmem(), os_free_bytes: freemem(), load_average: loadavg() },
  };
  if (process.platform !== "darwin" || !appPath) {
    result.observations_unavailable.push("darwin_native_host_sampling");
    return result;
  }
  const [table, memory, disk] = await Promise.all([
    probe("/bin/ps", ["-axww", "-o", "pid=,ppid=,lstart=,%cpu=,rss=,command="]),
    probe("/usr/bin/memory_pressure", ["-Q"]),
    probe("/usr/sbin/iostat", ["-Id", "-c", "1"]),
  ]);
  const percentage = memory.value?.match(/System-wide memory free percentage:\s*(\d+)%/u);
  result.host.memory_pressure_free_percent = percentage ? Number(percentage[1]) : null;
  result.host.iostat_since_boot = disk.value ?? null;
  if (!percentage) result.observations_unavailable.push("memory_pressure");
  if (!disk.value) result.observations_unavailable.push("iostat");
  if (table.value === undefined) {
    result.observations_unavailable.push("native_process_table");
    return result;
  }

  const all = parseDarwinProcessTable(table.value);
  const owns = new Set(all.filter(row => row.command.replace(/^"/u, "").startsWith(appPath + "/")).map(row => row.pid));
  const byPid = new Map(all.map(row => [row.pid, row]));
  const known = new Set(previouslyTracked.map(row => `${row.pid}:${row.started_at}:${row.command_sha256}`));
  function belongsToApp(row) {
    for (let current = row; current; current = byPid.get(current.parent_pid)) {
      if (owns.has(current.pid)) return true;
      if (!current.parent_pid || current.parent_pid === current.pid) break;
    }
    return false;
  }
  result.processes = all.flatMap(row => {
    const role = nativeInfrastructureRole(row);
    if (!role || (!belongsToApp(row) && !known.has(`${row.pid}:${row.started_at}:${row.command_sha256}`))) return [];
    const { command, ...identity } = row;
    return [{ ...identity, role }];
  });
  if (result.processes.length) {
    const usage = await probe("/usr/bin/python3", [counters, ...result.processes.map(row => String(row.pid))]);
    if (usage.value) {
      const byPid = new Map(JSON.parse(usage.value).map(row => [row.pid, row]));
      for (const row of result.processes) row.disk_io = byPid.get(row.pid) ?? null;
    } else {
      result.observations_unavailable.push("proc_pid_rusage");
    }
  }
  result.finished_at = new Date().toISOString();
  return result;
}
