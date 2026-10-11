// QA fixture only. Reads ordinary web APIs; never replaces browser getters.
async function fpDigest(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    x => x.toString(16).padStart(2, '0')).join('');
}
function fpCanvas(width = 32, height = 24) {
  return typeof document === 'undefined' ? new OffscreenCanvas(width, height) :
    Object.assign(document.createElement('canvas'), {width, height});
}
function fpPaint(canvas, alpha = 1) {
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  ctx.fillStyle = `rgba(43,87,131,${alpha})`;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = `rgba(198,146,72,${alpha})`;
  ctx.fillRect(2, 3, 9, 7);
  return ctx;
}
function fpHex(bytes) { return Array.from(bytes, x => x.toString(16).padStart(2, '0')).join(''); }
async function fpEncodedPixels(canvas, blob) {
  if (!blob) throw new Error('Null PNG blob');
  const bitmap = await createImageBitmap(blob);
  const destination = fpCanvas(canvas.width, canvas.height);
  const ctx = destination.getContext('2d', {willReadFrequently: true});
  ctx.drawImage(bitmap, 0, 0); bitmap.close();
  return fpHex(ctx.getImageData(0, 0, canvas.width, canvas.height).data);
}
async function fpReadCanvas(forceOffscreen = false) {
  const canvas = forceOffscreen ? new OffscreenCanvas(32,24) : fpCanvas(); const ctx = fpPaint(canvas);
  const first = ctx.getImageData(0, 0, 32, 24);
  const original = fpHex(first.data);
  const result = {kind:canvas.toBlob ? 'HTMLCanvas' : 'OffscreenCanvas', first: original, repeated: fpHex(ctx.getImageData(0,0,32,24).data),
    subrect: fpHex(ctx.getImageData(4,5,7,8).data), outOfBounds: fpHex(ctx.getImageData(-1,-1,1,1).data)};
  if (canvas.toBlob) {
    result.blob = await fpEncodedPixels(canvas, await new Promise(resolve => canvas.toBlob(resolve, 'image/png')));
    result.dataURL = await fpEncodedPixels(canvas, await (await fetch(canvas.toDataURL('image/png'))).blob());
  } else result.blob = await fpEncodedPixels(canvas, await canvas.convertToBlob({type: 'image/png'}));
  result.afterExports = fpHex(ctx.getImageData(0,0,32,24).data);
  ctx.putImageData(first, 0, 0);
  result.putImageData = fpHex(ctx.getImageData(0,0,32,24).data);
  ctx.clearRect(0,0,32,24);
  result.cleared = (ctx.getImageData(0,0,32,24).data).every(x => x === 0);
  // Explicitly expose known unsupported bypass surfaces rather than report them as protected.
  const translucent = fpPaint(fpCanvas(), 0.5);
  result.translucent = fpHex(translucent.getImageData(0,0,32,24).data);
  try {
    const p3 = fpCanvas().getContext('2d', {colorSpace: 'display-p3', willReadFrequently: true});
    p3.fillStyle = 'rgb(43,87,131)'; p3.fillRect(0,0,32,24);
    const data = p3.getImageData(0,0,32,24,{colorSpace:'display-p3'});
    result.displayP3 = {colorSpace:data.colorSpace, pixels:fpHex(data.data)};
  } catch(error) { result.displayP3 = {unsupported:String(error)}; }
  try {
    const f16 = fpPaint(fpCanvas()).getImageData(0,0,32,24,{pixelFormat:'rgba-float16'});
    result.float16 = {pixelFormat:f16.pixelFormat, digest:await fpDigest(new Uint8Array(f16.data.buffer))};
  } catch(error) { result.float16 = {unsupported:String(error)}; }
  return result;
}
async function fpReadSurface() {
  const result = {hardwareConcurrency:navigator.hardwareConcurrency,
    deviceMemory:navigator.deviceMemory ?? null,
    timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
    winterOffset:new Date('2026-01-15T12:00:00Z').getTimezoneOffset(),
    summerOffset:new Date('2026-07-15T12:00:00Z').getTimezoneOffset(),
    beforeDst:new Date('2026-03-29T00:30:00Z').getTimezoneOffset(),
    afterDst:new Date('2026-03-29T01:30:00Z').getTimezoneOffset(),
    userAgent:navigator.userAgent, platform:navigator.platform};
  try { result.canvas = await fpReadCanvas(); }
  catch(error) { result.canvas = {error:String(error)}; }
  try { result.requestHeaders = await (await fetch('/headers?token='+CONFIG.token)).json(); }
  catch(error) { result.requestHeaders = {error:String(error)}; }
  return result;
}
async function fpLargeCanvas() {
  const canvas = fpCanvas(2048,2048); const ctx = fpPaint(canvas);
  const times=[]; let digest='';
  for(let i=0;i<3;i++) {
    const start=performance.now(); const data=ctx.getImageData(0,0,2048,2048).data;
    times.push(performance.now()-start); digest=await fpDigest(data);
  }
  const start=performance.now();
  const blob=canvas.toBlob ? await new Promise(resolve=>canvas.toBlob(resolve,'image/png')) :
    await canvas.convertToBlob({type:'image/png'});
  return {width:2048,height:2048,readbackMs:times,pngMs:performance.now()-start,
    pngBytes:blob?.size ?? null,lastDigest:digest,
    jsHeap:performance.memory ? {used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize} :
      {unsupported:'performance.memory unavailable; native job peak recorded separately'}};
}
