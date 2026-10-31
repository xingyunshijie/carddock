const assert=require('node:assert/strict');
const {createTracker}=require('../app/static/notifications.js');
const job=(id,status,created=1)=>({id,status,created});
const tracker=createTracker({},100);
assert.equal(tracker.update([job('historic','failed')]).events.length,0,'opening history stays quiet');
assert.equal(tracker.update([job('a','running')]).events.length,0);
assert.deepEqual(tracker.update([job('a','completed')]).events.map(e=>e.kind),['complete']);
assert.equal(tracker.update([job('a','completed')]).events.length,0,'polls do not repeat a cue');
for(const status of ['failed','interrupted','cancelled','completed-with-skips']){
 const t=createTracker({a:'running'},100);
 assert.equal(t.update([job('a',status)]).events[0].kind,'problem',status);
 assert.equal(t.update([job('a',status)]).events.length,0,status+' repeats');
}
const fast=createTracker({},100);fast.remember('fast');
assert.equal(fast.update([job('fast','completed')]).events[0].kind,'complete','tiny manual jobs notify even if complete before polling');
const automatic=createTracker({},100);
assert.equal(automatic.update([job('auto','completed',101)]).events[0].kind,'complete','new automatic jobs notify between polls');
const initial=createTracker({},100);const saved=initial.update([job('restart','running')]).states;
assert.equal(createTracker(saved,100).update([job('restart','interrupted')]).events[0].kind,'problem','reload retains unfinished task observation');
const paused=createTracker({a:'running'},100);
assert.equal(paused.update([job('a','paused')]).events.length,0);
assert.equal(paused.update([job('a','running')]).events.length,0);
console.log('Completion, failure, interruption, fast tasks, reload and deduplication checks passed');

const paging=createTracker({},100);paging.update([job('recent','completed',101)]);paging.update([]);assert.equal(paging.update([job('recent','completed',101)]).events.length,0,'history paging does not repeat a completed cue');
