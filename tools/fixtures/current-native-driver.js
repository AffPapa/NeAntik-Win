// CONFIG and fpReadSurface are provided by the loopback-only QA server.
const early = {hardwareConcurrency:navigator.hardwareConcurrency, deviceMemory:navigator.deviceMemory ?? null,
  timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
  winterOffset:new Date('2026-01-15T12:00:00Z').getTimezoneOffset(),
  summerOffset:new Date('2026-07-15T12:00:00Z').getTimezoneOffset(),
  beforeDst:new Date('2026-03-29T00:30:00Z').getTimezoneOffset(),
  afterDst:new Date('2026-03-29T01:30:00Z').getTimezoneOffset()};
function bounded(promise, label) {
  return Promise.race([promise,new Promise(resolve=>setTimeout(()=>resolve({error:label+' timed out'}),15000))]);
}
function frame(origin,label) {
  return bounded(new Promise(resolve=>{
    const element=document.createElement('iframe');
    element.allow='ch-device-memory '+origin;
    const handler=event=>{if(event.source===element.contentWindow && event.data?.label===label){
      removeEventListener('message',handler); resolve(event.data.result); element.remove();}};
    addEventListener('message',handler);
    element.src=origin+'/frame?token='+CONFIG.token+'&label='+label; document.body.append(element);
  }),label);
}
function dedicated() {
  return bounded(new Promise(resolve=>{
    const worker=new Worker('/worker.js?token='+CONFIG.token);
    worker.onmessage=event=>{worker.terminate();resolve(event.data)};
    worker.onerror=event=>{worker.terminate();resolve({error:event.message})};
  }),'dedicatedWorker');
}
function shared() {
  if(!globalThis.SharedWorker) return Promise.resolve({error:'SharedWorker unavailable'});
  return bounded(new Promise(resolve=>{
    const worker=new SharedWorker('/shared.js?token='+CONFIG.token);
    worker.port.onmessage=event=>{worker.port.close();resolve(event.data)};worker.port.start();
    worker.onerror=event=>{worker.port.close();resolve({error:event.message})};
  }),'sharedWorker');
}
async function service() {
  if(!navigator.serviceWorker) return {error:'ServiceWorker unavailable'};
  let registration;
  try {
    registration=await navigator.serviceWorker.register('/service.js?token='+CONFIG.token, {scope:'/'});
    const worker=registration.installing || registration.waiting || registration.active;
    if(worker.state!=='activated') await bounded(new Promise(resolve=>{
      worker.addEventListener('statechange',()=>{if(worker.state==='activated')resolve()});
    }),'serviceWorker activation');
    if(!registration.active) throw new Error('Service worker did not activate');
    return await bounded(new Promise(resolve=>{
      const channel=new MessageChannel();
      channel.port1.onmessage=event=>{channel.port1.close();resolve(event.data)};
      registration.active.postMessage('read',[channel.port2]);
    }),'serviceWorker');
  } catch(error) {return {error:String(error)}}
  finally {if(registration) await registration.unregister()}
}
(async()=>{
  let result;
  try {
    const [main,sameIframe,crossIframe,dedicatedWorker,sharedWorker,serviceWorker]=await Promise.all([
      bounded(fpReadSurface(),'main'),frame(location.origin,'same'),frame(CONFIG.cross,'cross'),
      dedicated(),shared(),bounded(service(),'service registration')]);
    const offscreen=await (async()=>{try {return await fpReadCanvas(true)}catch(error){return {error:String(error)}}})();
    result={token:CONFIG.token,early,main,sameIframe,crossIframe,dedicatedWorker,sharedWorker,serviceWorker,
      offscreen,largeCanvas:await fpLargeCanvas()};
  } catch(error) {result={token:CONFIG.token,error:String(error)}}
  document.getElementById('current-native-result').textContent=JSON.stringify(result);
  await fetch('/report?token='+CONFIG.token,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});
})();
