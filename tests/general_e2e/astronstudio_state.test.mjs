import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import test from 'node:test';
import { queryNativeSessions, queryTerminalFinalResponse } from '../../tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs';

test('completed turn binds its named final message rather than a newer commentary', async () => {
  const root = await mkdtemp(join(tmpdir(), 'astronstudio-bound-final-'));
  const file = join(root, 'state.sqlite');
  const db = new DatabaseSync(file);
  try {
    db.exec(`CREATE TABLE projection_turns(thread_id TEXT,turn_id TEXT,state TEXT,assistant_message_id TEXT,checkpoint_turn_count INTEGER);
      CREATE TABLE projection_thread_messages(thread_id TEXT,turn_id TEXT,message_id TEXT,role TEXT,is_streaming INTEGER,text TEXT,sequence INTEGER);
      INSERT INTO projection_turns VALUES('thread','turn','completed','final',NULL);
      INSERT INTO projection_thread_messages VALUES('thread','turn','commentary','assistant',0,'still working',99);
      INSERT INTO projection_thread_messages VALUES('thread','turn','final','assistant',0,'actual final',2);`);
    const read = () => queryTerminalFinalResponse(file, 'thread', 'turn');
    assert.deepEqual(await read(), { ready: true, text: 'actual final', message_id: 'final', source: 'completed-turn.assistant_message_id' });
    db.exec("UPDATE projection_thread_messages SET is_streaming=1 WHERE message_id='final'");
    assert.equal((await read()).ready, false);
    db.exec("UPDATE projection_thread_messages SET is_streaming=0,text='' WHERE message_id='final'");
    assert.equal((await read()).ready, true);
    assert.equal((await read()).text, '');
    db.exec("UPDATE projection_thread_messages SET turn_id='other' WHERE message_id='final'");
    assert.equal((await read()).ready, false);
    db.exec("UPDATE projection_thread_messages SET turn_id='turn' WHERE message_id='final'");
    db.exec("UPDATE projection_turns SET assistant_message_id='not-materialized'");
    assert.equal((await read()).ready, false);
  } finally { db.close(); await rm(root, {recursive:true,force:true}); }
});

test('completed sessions reject active/unknown evidence but accept an old usage-only orphan', async () => {
  const root = await mkdtemp(join(tmpdir(), 'astronstudio-orphan-usage-'));
  const file = join(root, 'state.sqlite');
  const db = new DatabaseSync(file);
  try {
    db.exec(`
      CREATE TABLE projection_threads(thread_id TEXT,project_id TEXT,latest_turn_id TEXT,deleted_at TEXT);
      CREATE TABLE projection_projects(project_id TEXT,workspace_root TEXT,deleted_at TEXT);
      CREATE TABLE projection_turns(row_id INTEGER,thread_id TEXT,turn_id TEXT,state TEXT,termination_origin TEXT,requested_at TEXT,started_at TEXT,completed_at TEXT,checkpoint_turn_count INTEGER);
      CREATE TABLE projection_thread_sessions(thread_id TEXT,status TEXT,active_turn_id TEXT,last_error TEXT,updated_at TEXT);
      CREATE TABLE projection_pending_interactions(thread_id TEXT,status TEXT);
      CREATE TABLE provider_session_runtime(thread_id TEXT,resume_cursor_json TEXT);
      CREATE TABLE provider_runtime_open_turns(thread_id TEXT,turn_id TEXT,updated_at TEXT);
      CREATE TABLE provider_runtime_events(thread_id TEXT,turn_id TEXT,event_type TEXT,persisted_at TEXT);
      INSERT INTO projection_threads VALUES('thread','project','head',NULL);
      INSERT INTO projection_projects VALUES('project','/tmp/workspace',NULL);
      INSERT INTO projection_turns VALUES(1,'thread','head','completed',NULL,'2026-10-12T01:00:00Z','2026-10-12T01:00:00Z','2026-10-12T01:01:00Z',NULL);
      INSERT INTO projection_thread_sessions VALUES('thread','ready',NULL,NULL,'2026-10-12T01:01:00Z');
      INSERT INTO provider_session_runtime VALUES('thread','{"threadId":"session"}');
      INSERT INTO provider_runtime_open_turns VALUES('thread','orphan','2026-10-12T01:00:00Z');
      INSERT INTO provider_runtime_events VALUES('thread','orphan','thread.token-usage.updated','2026-10-12T01:00:00Z');
    `);
    const status = async () => (await queryNativeSessions(file))[0].status;
    assert.equal(await status(), 'completed');
    const checks = [
      ["UPDATE provider_runtime_events SET event_type='turn.started'", "UPDATE provider_runtime_events SET event_type='thread.token-usage.updated'"],
      ["UPDATE provider_runtime_events SET event_type=NULL", "UPDATE provider_runtime_events SET event_type='thread.token-usage.updated'"],
      ["UPDATE provider_runtime_events SET persisted_at='invalid'", "UPDATE provider_runtime_events SET persisted_at='2026-10-12T01:00:00Z'"],
      ["UPDATE provider_runtime_events SET persisted_at='2026-10-12T01:02:00Z'", "UPDATE provider_runtime_events SET persisted_at='2026-10-12T01:00:00Z'"],
      ["UPDATE provider_runtime_open_turns SET updated_at='invalid'", "UPDATE provider_runtime_open_turns SET updated_at='2026-10-12T01:00:00Z'"],
      ["UPDATE provider_runtime_open_turns SET updated_at='2026-10-12T01:02:00Z'", "UPDATE provider_runtime_open_turns SET updated_at='2026-10-12T01:00:00Z'"],
      ["UPDATE projection_thread_sessions SET status='running'", "UPDATE projection_thread_sessions SET status='ready'"],
      ["UPDATE projection_thread_sessions SET status=NULL", "UPDATE projection_thread_sessions SET status='ready'"],
      ["UPDATE projection_threads SET latest_turn_id=NULL", "UPDATE projection_threads SET latest_turn_id='head'"],
      ["UPDATE projection_thread_sessions SET active_turn_id='active'", "UPDATE projection_thread_sessions SET active_turn_id=NULL"],
      ["UPDATE projection_turns SET state='running'", "UPDATE projection_turns SET state='completed'"],
      ["UPDATE projection_turns SET completed_at=NULL", "UPDATE projection_turns SET completed_at='2026-10-12T01:01:00Z'"],
      ["INSERT INTO projection_turns VALUES(2,'thread','orphan','completed',NULL,NULL,NULL,'2026-10-12T01:00:00Z',NULL)", "DELETE FROM projection_turns WHERE turn_id='orphan'"],
      ["DELETE FROM provider_runtime_events", "INSERT INTO provider_runtime_events VALUES('thread','orphan','thread.token-usage.updated','2026-10-12T01:00:00Z')"],
    ];
    for (const [change, restore] of checks) {
      db.exec(change);
      assert.equal(await status(), 'running', change);
      db.exec(restore);
      assert.equal(await status(), 'completed', restore);
    }
    db.exec("INSERT INTO projection_pending_interactions VALUES('thread','pending')");
    assert.equal(await status(), 'needs_attention');
  } finally {
    db.close();
    await rm(root, { recursive: true, force: true });
  }
});
