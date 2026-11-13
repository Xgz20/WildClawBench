import {runCapture} from '../../vendor/e2e-shared/desktop-runtime/process.mjs';

export function parseNativeForegroundApp(front, info) {
  const asn = String(front).trim();
  if (!/^ASN:0x[0-9a-f]+-0x[0-9a-f]+:$/iu.test(asn)) throw Error('ASTRONSTUDIO_NATIVE_FOREGROUND_ASN_INVALID');
  const pids = [...String(info).matchAll(/^"pid"=(\d+)\s*$/gmu)];
  const bundles = [...String(info).matchAll(/^"CFBundleIdentifier"="([^"\r\n]+)"\s*$/gmu)];
  if (pids.length !== 1 || bundles.length !== 1 || Number(pids[0][1]) <= 1) throw Error('ASTRONSTUDIO_NATIVE_FOREGROUND_INFO_INVALID');
  return {asn, pid:Number(pids[0][1]), bundle_id:bundles[0][1]};
}

export async function readNativeForegroundApp(overrides={}) {
  const run = overrides.runCommand || runCapture;
  const front = await run('/usr/bin/lsappinfo',['front'],{capture:true,allowFailure:true,timeoutMs:5000});
  if (front.code !== 0 || !/^ASN:0x[0-9a-f]+-0x[0-9a-f]+:$/iu.test(String(front.stdout).trim())) throw Error('ASTRONSTUDIO_NATIVE_FOREGROUND_READ_FAILED');
  const info = await run('/usr/bin/lsappinfo',['info','-only','bundleid,pid',String(front.stdout).trim()],{capture:true,allowFailure:true,timeoutMs:5000});
  if (info.code !== 0) throw Error('ASTRONSTUDIO_NATIVE_FOREGROUND_INFO_FAILED');
  return parseNativeForegroundApp(front.stdout,info.stdout);
}
