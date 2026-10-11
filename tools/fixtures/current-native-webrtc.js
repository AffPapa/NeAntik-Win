// Observations only: no WebRTC API replacement or CDP override.
(async()=>{
  const output={token:CONFIG.token,peerConnectionAvailable:!!globalThis.RTCPeerConnection,
    candidates:[],iceGatheringState:null,error:null};
  let peer;
  try {
    peer=new RTCPeerConnection({iceServers:[{urls:CONFIG.stunUrl}],iceCandidatePoolSize:0});
    peer.onicecandidate=event=>{if(event.candidate)output.candidates.push(event.candidate.candidate)};
    peer.createDataChannel('owned-native-qa');
    await peer.setLocalDescription(await peer.createOffer());
    // Keep the same bounded allocation window for control and protected visits.
    await new Promise(resolve=>setTimeout(resolve,7000));
    output.iceGatheringState=peer.iceGatheringState;
  } catch(error) {output.error=String(error)}
  finally {if(peer)peer.close()}
  document.getElementById('current-webrtc-result').textContent=JSON.stringify(output);
  await fetch('/report?token='+CONFIG.token,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(output)});
})();
