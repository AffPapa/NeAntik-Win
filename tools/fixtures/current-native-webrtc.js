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
    // Observe actual ICE completion where possible. A fixed seven-second
    // sample left the owned positive control in "gathering" on Windows.
    await new Promise(resolve=>{
      if(peer.iceGatheringState==='complete') return resolve();
      let finished=false;
      const done=()=>{if(finished)return;finished=true;clearTimeout(timer);
        peer.removeEventListener('icegatheringstatechange',changed);resolve();};
      const changed=()=>{if(peer.iceGatheringState==='complete')done();};
      const timer=setTimeout(done,18000);
      peer.addEventListener('icegatheringstatechange',changed);
      changed();
    });
    output.iceGatheringState=peer.iceGatheringState;
  } catch(error) {output.error=String(error)}
  finally {if(peer)peer.close()}
  document.getElementById('current-webrtc-result').textContent=JSON.stringify(output);
  await fetch('/report?token='+CONFIG.token,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(output)});
})();
