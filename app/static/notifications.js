/* State transitions are separate from browser audio so notices remain deterministic. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.CardDockNotifications=factory()})(typeof globalThis==='object'?globalThis:this,function(){
 const terminal=new Set(['completed','completed-with-skips','failed','cancelled','interrupted']);
 return {createTracker(previous={},startedAt=Date.now()/1000){
  const states={...previous};
  return {remember(id){if(!states[id])states[id]='queued';return {...states}},update(jobs){
   const events=[];let changed=false;
   for(const job of jobs){const old=states[job.id];if(old!==job.status){states[job.id]=job.status;changed=true;if(terminal.has(job.status)&&(old||job.created>=startedAt))events.push({id:job.id,status:job.status,kind:job.status==='completed'?'complete':'problem'})}}
   const ids=new Set(jobs.map(j=>j.id));let excess=Object.keys(states).length-512;for(const id of Object.keys(states))if(excess>0&&!ids.has(id)){delete states[id];changed=true;excess--}
   return {events,changed,states:{...states}};
  }};
 }};
});
