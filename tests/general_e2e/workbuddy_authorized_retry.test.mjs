import assert from "node:assert/strict";
import test from "node:test";
import {validateRetryAuthorization} from "../../tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/retry-terminal-review.mjs";
function fixture(){return {m:{schema_version:"wildclawbench.workbuddy-authorized-terminal-retry/v1",task_id:"task",old_attempt_id:"old",new_attempt_id:"new",user_authorization:"用户明确授权仅重跑该题"},q:{tasks:[{task_id:"task",attempt_id:"old",phase:"NEEDS_ATTENTION",dispatch_attempt_count:1}],terminal_reviews:[{task_id:"task",attempt_id:"old",native_terminal_observed:true}]}}}
test("a new authorized attempt requires the exact registered cancelled original",()=>{const {m,q}=fixture();const r=validateRetryAuthorization(m,q);assert.equal(r.row.attempt_id,"old");assert.equal(q.tasks[0].phase,"NEEDS_ATTENTION");});
test("uncertain sends without a terminal proof cannot be retried",()=>{const {m,q}=fixture();q.terminal_reviews=[];assert.throws(()=>validateRetryAuthorization(m,q),/CANCELLED_REVIEW_REQUIRED/);});
test("authorization cannot replay the same original attempt",()=>{const {m,q}=fixture();m.new_attempt_id="old";assert.throws(()=>validateRetryAuthorization(m,q),/AUTHORIZATION_REQUIRED/);});
test("missing authorization and a foreign original attempt fail closed",()=>{const {m,q}=fixture();m.user_authorization="";assert.throws(()=>validateRetryAuthorization(m,q),/AUTHORIZATION_REQUIRED/);m.user_authorization="allowed";m.old_attempt_id="foreign";assert.throws(()=>validateRetryAuthorization(m,q),/CANCELLED_REVIEW_REQUIRED/);});
