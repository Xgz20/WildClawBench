"""Independent observable-protocol oracle, frozen before reference repair.
No reference patch imports, private worker-state assertions, network, or clocks.
Watchdogs only bound a broken program; pass/fail is public lifecycle behavior.
"""
import asyncio
import collections
import importlib
import random
import sys
import unittest
from pathlib import Path

PROGRAM = None

class WorkFault(Exception): pass
class PublishFault(Exception): pass
class AcquireFault(Exception): pass

class ProbePool:
    def __init__(self, *, acquire_gate=None, release_gate=None, acquire_error=False):
        self.acquire_gate, self.release_gate = acquire_gate, release_gate
        self.acquire_error = acquire_error
        self.acquire_entered, self.release_entered = asyncio.Event(), asyncio.Event()
        self.attempts, self.issued, self.releases = [], [], []
        self.active, self.peak, self.interrupted_release = {}, 0, 0
    async def acquire(self, item):
        self.attempts.append(item);self.acquire_entered.set()
        if self.acquire_gate is not None:await self.acquire_gate.wait()
        if self.acquire_error:raise AcquireFault("acquire rejected before ownership")
        token=object();self.active[token]=item;self.issued.append((item,token));self.peak=max(self.peak,len(self.active))
        return token
    async def release(self, token):
        self.releases.append(token);self.release_entered.set()
        if token not in self.active:raise RuntimeError("release without ownership or duplicate release")
        try:
            if self.release_gate is not None:await self.release_gate.wait()
            else:await asyncio.sleep(0)
        except asyncio.CancelledError:
            self.interrupted_release+=1;raise
        del self.active[token]

class ProbeSink:
    def __init__(self, *, gate=None, fail_before=False, fail_after=False):
        self.gate,self.fail_before,self.fail_after=gate,fail_before,fail_after
        self.attempts,self.records=[],[];self.accepted=asyncio.Event();self.active=0
    async def emit(self,item,status,*,value=None,error=None):
        self.active+=1;self.attempts.append((item,status))
        try:
            if self.fail_before:raise PublishFault("rejected before acceptance")
            if any(r[0]==item for r in self.records):raise RuntimeError("second terminal for same item")
            self.records.append((item,status,value,error));self.accepted.set()
            if self.gate is not None:await self.gate.wait()
            else:await asyncio.sleep(0)
            if self.fail_after:raise PublishFault("ack failed after acceptance")
        finally:self.active-=1

class ProbeWork:
    def __init__(self,pool,items,*,gates=None,errors=None,values=None):
        self.pool=pool;self.entered={x:asyncio.Event() for x in items};self.gates=gates or {};self.errors=errors or {};self.values=values or {x:{"value":x,"rank":i} for i,x in enumerate(items)};self.active=set();self.calls=[]
    async def __call__(self,item,lease):
        if self.pool.active.get(lease)!=item:raise AssertionError("wrong opaque lease passed to work")
        self.calls.append(item);self.active.add(item);self.entered[item].set()
        try:
            if item in self.gates:await self.gates[item].wait()
            else:await asyncio.sleep(0)
            if item in self.errors:raise self.errors[item]
            return self.values[item]
        finally:self.active.remove(item)

def load_worker():
    for name in list(sys.modules):
        if name=='project' or name.startswith('project.'):del sys.modules[name]
    root=str(Path(PROGRAM).resolve())
    if root not in sys.path:sys.path.insert(0,root)
    importlib.invalidate_caches()
    return importlib.import_module('project.worker')

class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stage='candidate_import';self.details=[];self.module=load_worker();self.stage='scenario';self.gates=[];self.baseline_tasks=set()
        if not callable(getattr(self.module,'run_batch',None)):raise AssertionError('public run_batch missing')
        error=getattr(self.module,'BatchTimeoutError',None)
        if not isinstance(error,type) or not issubclass(error,TimeoutError):raise AssertionError('public BatchTimeoutError type missing')
    async def asyncSetUp(self):self.baseline_tasks=set(asyncio.all_tasks())
    def gate(self,opened=False):
        e=asyncio.Event();self.gates.append(e)
        if opened:e.set()
        return e
    def launch(self,items,pool,work,sink,**kw):return asyncio.create_task(self.module.run_batch(items,pool,work,sink,**kw))
    async def observe_terminal(self,awaitable,label):
        try:
            value=await awaitable;row={'label':label,'outcome':'returned','value':value}
        except (Exception,asyncio.CancelledError) as error:row={'label':label,'outcome':'raised','error_type':type(error).__name__}
        self.details.append(row)
    async def checkpoint(self,event,task):
        waiter=asyncio.create_task(event.wait())
        try:
            done,_=await asyncio.wait({waiter,task},return_when=asyncio.FIRST_COMPLETED,timeout=8)
            if waiter not in done:
                if task.done():
                    if not task.cancelled():task.exception()
                    raise AssertionError('processor ended before the controlled checkpoint')
                raise AssertionError('liveness watchdog: controlled checkpoint was not reached')
        finally:
            waiter.cancel();await asyncio.gather(waiter,return_exceptions=True)
    def snapshot(self,pool,work,sink,label):
        row={'label':label,'acquire_attempts':list(pool.attempts),'issued':[i for i,_ in pool.issued],'active_leases':list(pool.active.values()),'release_calls':len(pool.releases),'release_duplicates':len(pool.releases)-len(set(pool.releases)),'release_interrupted':pool.interrupted_release,'peak_leases':pool.peak,'work_calls':list(work.calls),'active_work':sorted(work.active),'terminal_attempts':[list(x) for x in sink.attempts],'terminals':[{'item':r[0],'status':r[1],'value':r[2],'error_type':type(r[3]).__name__ if r[3] else None} for r in sink.records],'active_emits':sink.active}
        self.details.append(row);return row
    def balanced(self,pool,work,sink,limit,label,*,rejected=False):
        self.snapshot(pool,work,sink,label)
        self.assertFalse(pool.active,'lease remains at observable batch terminal')
        self.assertFalse(work.active,'work remains active at batch terminal')
        self.assertEqual(sink.active,0,'emit remains active at batch terminal')
        self.assertLessEqual(pool.peak,limit)
        issued=[token for _,token in pool.issued]
        self.assertEqual(collections.Counter(pool.releases),collections.Counter(issued),'each successfully acquired token must be released once')
        attempts=collections.Counter(x[0] for x in sink.attempts)
        self.assertEqual(set(attempts),{item for item,_ in pool.issued})
        self.assertTrue(all(n==1 for n in attempts.values()),'terminal submission retried')
        expected=0 if rejected else len(issued)
        self.assertEqual(len(sink.records),expected)
        pending=[t for t in asyncio.all_tasks() if t not in self.baseline_tasks and t is not asyncio.current_task() and not t.done()]
        self.assertFalse(pending,'owned work/deadline/cleanup task remains after run_batch terminates')
    async def asyncTearDown(self):
        for e in getattr(self,'gates',[]):e.set()
        pending=[t for t in asyncio.all_tasks() if t not in self.baseline_tasks and t is not asyncio.current_task() and not t.done()]
        for t in pending:t.cancel()
        if pending:await asyncio.wait_for(asyncio.gather(*pending,return_exceptions=True),timeout=8)

    async def test_B01_success_order_limit_and_reentry(self):
        ids=['请求-'+format(x,'x') for x in random.Random(2026102643).sample(range(100,999),4)]
        for revision in (1,2):
            pool,sink=ProbePool(),ProbeSink();first=self.gate();work=ProbeWork(pool,ids,gates={ids[0]:first},values={x:(revision,x[::-1]) for x in ids})
            task=self.launch(iter(ids),pool,work,sink,concurrency=2)
            await self.checkpoint(work.entered[ids[1]],task);first.set()
            values=await task;self.assertEqual(values,[work.values[x] for x in ids]);self.assertEqual({r[1] for r in sink.records},{'succeeded'});self.balanced(pool,work,sink,2,'success/reentry '+str(revision))

    async def test_B02_work_failure_drains_siblings(self):
        ids=['fail-owner','already-running','queued'];go=self.gate();hold=self.gate();pool,sink=ProbePool(),ProbeSink();work=ProbeWork(pool,ids,gates={ids[0]:go,ids[1]:hold},errors={ids[0]:WorkFault('distinct work fault')})
        task=self.launch(ids,pool,work,sink,concurrency=2);await self.checkpoint(work.entered[ids[1]],task);go.set()
        with self.assertRaises(WorkFault):await task
        self.balanced(pool,work,sink,2,'failure drains acquired and queued work')
        owner=[r for r in sink.records if r[0]==ids[0]];self.assertEqual(len(owner),1);self.assertEqual(owner[0][1],'failed');self.assertIsInstance(owner[0][3],WorkFault)
        pool,sink=ProbePool(acquire_error=True),ProbeSink();work=ProbeWork(pool,['acquire-error-owner'])
        with self.assertRaises(AcquireFault):await self.module.run_batch(['acquire-error-owner'],pool,work,sink)
        self.balanced(pool,work,sink,2,'acquire error also remains a failure')

    async def test_B03_cancel_work_propagates_and_closes(self):
        ids=['cancel-owner'];hold=self.gate();pool,sink=ProbePool(),ProbeSink();work=ProbeWork(pool,ids,gates={ids[0]:hold});task=self.launch(ids,pool,work,sink)
        await self.checkpoint(work.entered[ids[0]],task);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.balanced(pool,work,sink,2,'caller cancellation');self.assertEqual([r[1] for r in sink.records],['cancelled'])

    async def test_B04_signalled_timeout_is_not_success(self):
        ids=['deadline-owner'];hold,deadline=self.gate(),self.gate();pool,sink=ProbePool(),ProbeSink();work=ProbeWork(pool,ids,gates={ids[0]:hold});task=self.launch(ids,pool,work,sink,deadline=deadline)
        await self.checkpoint(work.entered[ids[0]],task);deadline.set()
        with self.assertRaises(TimeoutError):await task
        self.balanced(pool,work,sink,2,'deadline closes before raising');self.assertEqual([r[1] for r in sink.records],['cancelled'])
        deadline=self.gate(True);pool,sink=ProbePool(),ProbeSink();work=ProbeWork(pool,['expired-before-start'])
        with self.assertRaises(TimeoutError):await self.module.run_batch(['expired-before-start'],pool,work,sink,deadline=deadline)
        self.balanced(pool,work,sink,2,'preexpired deadline is also failure')

    async def test_B05_publish_failures_do_not_retry_or_leak(self):
        for before in (True,False):
            ids=['publish-'+str(before)];pool=ProbePool();sink=ProbeSink(fail_before=before,fail_after=not before);work=ProbeWork(pool,ids)
            with self.assertRaises(PublishFault):await self.module.run_batch(ids,pool,work,sink)
            self.balanced(pool,work,sink,2,'publisher '+('before' if before else 'after')+' acceptance',rejected=before)
            self.assertEqual(sink.attempts,[(ids[0],'succeeded')])

    async def test_E01_cancel_pending_acquire_never_releases_unowned(self):
        ids=['pending-acquire'];gate=self.gate();pool,sink=ProbePool(acquire_gate=gate),ProbeSink();work=ProbeWork(pool,ids);task=self.launch(ids,pool,work,sink)
        await self.checkpoint(pool.acquire_entered,task);task.cancel()
        await self.observe_terminal(task,'acquire-cancel outcome, propagation owned by B03')
        self.balanced(pool,work,sink,2,'acquire cancellation');self.assertEqual((pool.issued,pool.releases,sink.attempts),([],[],[]))

    async def test_E02_repeated_cancel_during_cleanup_waits_once(self):
        ids=['cleanup-owner'];gate=self.gate();pool,sink=ProbePool(release_gate=gate),ProbeSink();work=ProbeWork(pool,ids);task=self.launch(ids,pool,work,sink)
        await self.checkpoint(pool.release_entered,task);task.cancel();await asyncio.sleep(0);task.cancel();await asyncio.sleep(0);gate.set()
        await self.observe_terminal(task,'cleanup-cancel outcome, propagation owned by B03')
        self.balanced(pool,work,sink,2,'repeated cancel while releasing');self.assertEqual(len(pool.releases),1);self.assertEqual([r[1] for r in sink.records],['succeeded'])

    async def test_E03_cancel_after_terminal_acceptance_does_not_reemit(self):
        ids=['accepted-terminal'];ack=self.gate();pool,sink=ProbePool(),ProbeSink(gate=ack);work=ProbeWork(pool,ids);task=self.launch(ids,pool,work,sink)
        await self.checkpoint(sink.accepted,task);task.cancel();ack.set()
        await self.observe_terminal(task,'ack-cancel outcome, propagation owned by B03')
        self.balanced(pool,work,sink,2,'cancel during terminal ack');self.assertEqual(sink.attempts,[(ids[0],'succeeded')])

    async def test_E04_failed_acquire_never_fabricates_ownership(self):
        ids=['failed-acquire'];pool,sink=ProbePool(acquire_error=True),ProbeSink();work=ProbeWork(pool,ids)
        await self.observe_terminal(self.module.run_batch(ids,pool,work,sink),'acquire-error outcome, error propagation owned by B02')
        self.balanced(pool,work,sink,2,'acquire raises before lease');self.assertEqual(work.calls,[])

    async def test_E05_preexpired_empty_validation_and_batch_isolation(self):
        deadline=self.gate(True);pool,sink=ProbePool(),ProbeSink();work=ProbeWork(pool,['never-admitted'])
        await self.observe_terminal(self.module.run_batch(['never-admitted'],pool,work,sink,deadline=deadline),'preexpired outcome, failure type owned by B04')
        self.balanced(pool,work,sink,2,'preexpired');self.assertEqual(pool.attempts,[])
        self.assertEqual(await self.module.run_batch([],pool,work,sink),[])
        for args in [(['duplicate','duplicate'],2),(['x'],0),([7],2)]:
            with self.assertRaises(ValueError):await self.module.run_batch(args[0],pool,work,sink,concurrency=args[1])
        self.assertEqual(pool.attempts,[])
        gate_a,gate_b=self.gate(),self.gate();pa,pb=ProbePool(),ProbePool();sa,sb=ProbeSink(),ProbeSink();wa,wb=ProbeWork(pa,['same-key'],gates={'same-key':gate_a}),ProbeWork(pb,['same-key'],gates={'same-key':gate_b},values={'same-key':{'independent':True}})
        ta,tb=self.launch(['same-key'],pa,wa,sa),self.launch(['same-key'],pb,wb,sb)
        await self.checkpoint(wa.entered['same-key'],ta);await self.checkpoint(wb.entered['same-key'],tb);ta.cancel()
        await self.observe_terminal(ta,'isolated-cancel outcome, propagation owned by B03')
        self.assertFalse(tb.done(),'one batch cancellation terminated another batch');gate_b.set();self.assertEqual(await tb,[{'independent':True}])
        self.balanced(pa,wa,sa,2,'isolated cancelled batch');self.balanced(pb,wb,sb,2,'isolated successful batch')
