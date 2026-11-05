/* adjustable-bed-card 4.3.0 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var zt=Object.defineProperty;var Ot=Object.getOwnPropertyDescriptor;var C=(n,s,e,t)=>{for(var i=t>1?void 0:t?Ot(s,e):s,o=n.length-1,r;o>=0;o--)(r=n[o])&&(i=(t?r(s,e,i):r(i))||i);return t&&i&&zt(s,e,i),i};function Me(n,s){let e=n?.entities[s],t=n?.states[s]?.attributes,i=t?.hold_release_button_key;if(!e?.device_id||typeof i!="string")return;let o=t?.bed_side,r=(o==="left"||o==="right")&&e.translation_key?.endsWith(`_${o}`)?`${i}_${o}`:i;return Object.values(n?.entities??{}).find(l=>l.device_id===e.device_id&&l.entity_id.startsWith("button.")&&l.translation_key===r)?.entity_id}function it(n,s){let e=n?.entities[s]?.device_id,t=n?.states[s]?.attributes,i=t?.held_control,o=t?.hold_start_delay_ms,r=t?.hold_release_delay_ms;if(!e||typeof i!="string"||typeof o!="number"||!Number.isFinite(o)||o<0||typeof r!="number"||!Number.isFinite(r)||r<0)return;let l=Me(n,s);if(!(typeof t?.hold_release_button_key=="string"&&!l))return{...l?{releaseButton:l}:{},key:s,up:s,deviceId:e,holdEntityId:s,heldControl:{control:i,startDelayMs:o,releaseDelayMs:r}}}function Re(n,s,e){if(s.timedMove)return n?.callService("adjustable_bed","timed_move",{device_id:s.timedMove.deviceId,...s.timedMove.side?{side:s.timedMove.side}:{},motor:s.timedMove.motor,direction:e,duration_ms:1e3});if(s.cover)return n?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:s.cover});let t=e==="up"?s.up:s.down;return t?n?.callService("button","press",{entity_id:t}):void 0}function st(n,s,e){let t=s.heldControls?.[e]??s.heldControl;if(!t||!s.deviceId)return;let i=n?.states[s.holdEntityId??s.cover??""]?.attributes.bed_side,o={device_id:[s.deviceId],control:t.control,duration:60};return(i==="left"||i==="right"||i==="both")&&(o.side=i),n?.callService("adjustable_bed","hold_control",o)}function ot(n,s,e){Re(n,s,e)?.catch(()=>{})}function nt(n,s,e,t){let i=()=>t(),o=()=>{e()&&t()};n.addEventListener("blur",i),s.addEventListener("visibilitychange",o);let r=!0;return()=>{r&&(r=!1,n.removeEventListener("blur",i),s.removeEventListener("visibilitychange",o))}}function rt(n,s){let e=s[n]?.parent_device_id??s[n]?.via_device_id;return e&&s[e]?e:void 0}function Lt(n,s){return Object.values(s).some(e=>(e.parent_device_id??e.via_device_id)===n)}var at={stop_left:"left",stop_right:"right",stop_both:"both"};function pe(n,s){let e=n.states[s]?.attributes,t=e?.bed_side??e?.side,i=t==="left"||t==="right"||t==="both"?t:void 0,o=n.entities[s]?.translation_key,r=o?at[o]:void 0;if(!(i&&r&&i!==r))return i??r}function tt(n,s){let e=n.entities[s];return e?.platform==="adjustable_bed"&&s.startsWith("button.")&&(e.translation_key==="stop"||e.translation_key!==void 0&&e.translation_key in at)}function X(n,s){if(!n||!s)return;let e=n.entities[s]?.device_id;if(!e)return;let t=n.devices??{},i=rt(e,t),o=pe(n,s)??(!i&&Lt(e,t)?"both":void 0);return{deviceId:i&&o?i:e,side:o,physicalDeviceId:e,...i?{parentDeviceId:i}:{},...o==="both"?{physicalChildIds:Object.entries(t).filter(([,r])=>(r.parent_device_id??r.via_device_id)===e).map(([r])=>r)}:{}}}function jt(n,s){return(n.parentDeviceId??n.deviceId)!==(s.parentDeviceId??s.deviceId)?!1:n.side==="both"||s.side==="both"?!0:n.side&&s.side?n.side===s.side:!n.physicalDeviceId||!s.physicalDeviceId||n.physicalDeviceId===s.physicalDeviceId}function Pe(n,s){if(!n||!s)return[];let e=n.entities[s]?.device_id;if(!e)return[];let t=pe(n,s);if(t==="left"||t==="right"){let h=t==="left"?"right":"left",f=Object.values(n.entities).filter(g=>g.entity_id!==s&&g.device_id===e&&tt(n,g.entity_id)&&pe(n,g.entity_id)===h);if(f.length===1)return[f[0].entity_id]}let i=n.devices??{},o=rt(e,i);if(!o)return[];let r=Object.entries(i).filter(([,h])=>(h.parent_device_id??h.via_device_id)===o).map(([h])=>h);if(r.length!==2||!r.includes(e))return[];let l=r.find(h=>h!==e),d=Object.values(n.entities).filter(h=>{if(h.device_id!==l||!tt(n,h.entity_id))return!1;let f=pe(n,h.entity_id);return f!=="both"&&(f===void 0||f!==t)});return d.length===1?[d[0].entity_id]:[]}function Ae(n){let s=n.holdEntityId??n.cover??n.up??n.down??"";return`${n.key}\0${s}`}var ue=class{constructor(s,e={setTimeout:(t,i)=>globalThis.setTimeout(t,i),clearTimeout:t=>globalThis.clearTimeout(t)}){this.actions=s;this.timers=e;this._key=null;this._motor=null;this._scopeStops=[];this._remainingStops=[];this._stopTargetGenerations=new Map;this._keyboardKey=null;this._motorId=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0;this._repeatBlocked=!1;this._started=!1;this._releaseId=0;this._pendingReleases=new Map}get heldKey(){return this._key}start(s,e,t,i,o=i?[i]:[],r=[],l=null,d){if(this._key!==null)return;let h=Array.isArray(o)?o:[];this._target=Array.isArray(o)?d:o,this._flushPendingForTarget(i??s.cover??s.key),this._key=s.key,this._motor=Object.freeze({...s,...s.timedMove?{timedMove:Object.freeze({...s.timedMove})}:{}}),this._motorId=Ae(s),this._cover=s.cover??null,this._stop=i??null,this._scopeStops=[...new Set([...h,...i?[i]:[],...s.cover?[s.cover]:[],...this._targetScope(this._target)])],this._remainingStops=[...new Set(r)],this.claimStopScope(this._scopeStops),this._pointerId=t,this._keyboardKey=l;let f=++this._generation;if(this._heldControl=s.heldControls?.[e]??s.heldControl,this._releaseButton=s.releaseButton,this._heldControl){let g=this._heldControl.startDelayMs;g<=0?this._startHeldControl(this._motor,e,f):this._startTimer=this.timers.setTimeout(()=>this._startHeldControl(this._motor??s,e,f),g);return}this._started=!0,this._repeat(this._motor,e,f)}_targetScope(s){if(!s)return[];let e=s.side==="left"||s.side==="right"?[s.side]:["left","right"];return[...new Set([s.deviceId,...s.physicalDeviceId?[s.physicalDeviceId]:[],...s.physicalChildIds??[]])].flatMap(i=>e.map(o=>`target:${i}:${o}`))}claimStopScope(s,e){for(let t of new Set([...s,...this._targetScope(e)]))this._stopTargetGenerations.set(t,(this._stopTargetGenerations.get(t)??0)+1)}_startHeldControl(s,e,t){this._startTimer=void 0,!(t!==this._generation||this._motorId!==Ae(s))&&(this._started=!0,this._holdControl(s,e,t))}async _holdControl(s,e,t){try{let i=this.actions.holdControl?.(s,e);i&&await i}catch{}finally{t===this._generation&&this._reset()}}async _repeat(s,e,t){let i=this._motor;if(i)for(;t===this._generation&&!this._repeatBlocked;)try{let o=this.actions.pulse(i,e);if(!o)return;this._pulseInFlight=o;try{await o}finally{this._pulseInFlight===o&&(this._pulseInFlight=void 0)}}catch{return}}_targetKey(s=this._stop??void 0,e=this._cover??void 0){return s??e??this._key??""}_release(s){return s.releaseButton?(this.actions.stopBed(s.releaseButton),s.releaseButton):s.cover?(this.actions.stopCover(s.cover,s.stopEntityId),s.cover):(this.actions.stopBed(s.stopEntityId),s.stopEntityId)}_scheduleRelease(){let s={id:++this._releaseId,releaseButton:this._releaseButton,motorKey:this._key??"",targetKey:this._targetKey(),target:this._target,cover:this._cover??void 0,stopEntityId:this._stop??void 0,scopeGenerations:new Map(this._scopeStops.map(t=>[t,this._stopTargetGenerations.get(t)??0]))};this._pendingReleases.set(s.id,s);let e=this._heldControl?.releaseDelayMs??0;if(e<=0){this._runRelease(s);return}s.timer=this.timers.setTimeout(()=>this._runRelease(s),e)}_runRelease(s){if(this._pendingReleases.delete(s.id)&&(s.timer!==void 0&&this.timers.clearTimeout(s.timer),[...s.scopeGenerations].every(([e,t])=>this._stopTargetGenerations.get(e)===t)))return this._release(s)}_flushPendingForTarget(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s&&(this._runRelease(t),e.add(i))}return e}_flushAllReleases(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s?(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer)):(this._runRelease(t),e.add(i))}return e}_targetsOverlap(s,e,t,i){return t!==void 0&&s===t?!0:!!e&&!!i&&jt(e,i)}_discardReleasesOverlapping(s,e){let t=!1;for(let i of[...this._pendingReleases.values()])!i.scopeGenerations.has(s)&&!this._targetsOverlap(i.targetKey,i.target,s,e)||(this._pendingReleases.delete(i.id),i.timer!==void 0&&this.timers.clearTimeout(i.timer),i.target?.side==="both"&&[...i.scopeGenerations].every(([o,r])=>this._stopTargetGenerations.get(o)===r)&&(t=!0));return t}_discardAllReleases(){for(let s of this._pendingReleases.values())s.timer!==void 0&&this.timers.clearTimeout(s.timer);this._pendingReleases.clear()}endFromPointer(s,e,t,i){this._pointerId===null||e!==this._pointerId||t&&(i!==void 0&&this._stop!==i||this.end(s,i))}endActiveFromPointer(s,e){!this._motor||this._pointerId===null||this.endFromPointer(this._motor,s,e)}endKeyboard(s,e,t){this._pointerId!==null||!this._motor||s&&!this._ownsRelease(s,e)||e!==void 0&&this._stop!==e||t!==void 0&&this._keyboardKey!==null&&this._keyboardKey!==t||this.end(this._motor)}end(s,e){if(!this._ownsRelease(s,e))return;let t=this._started,i=this._heldControl!==void 0,o={releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0};t&&i&&this._scheduleRelease(),this._reset(),!(!t||i)&&this._release(o)}_ownsRelease(s,e){return this._key!==s.key?!1:e===void 0?this._motorId===Ae(s):this._stop===e}cancel(s,e=!1){if(!s)return!1;let t=this._key===s.key;t&&this._reset();let i=!1;if(e)for(let o of[...this._pendingReleases.values()])o.motorKey===s.key&&(this._pendingReleases.delete(o.id),o.timer!==void 0&&this.timers.clearTimeout(o.timer),i=!0);return t||i}stopCover(s,e,t,i,o=[]){let r=s.cover;if(!r)return;let l=e!==void 0&&e.side!=="both",d=new Set,h=new Map,f,g=v=>{for(let $ of v)$!==i&&(d.add($),h.set($,this._stopTargetGenerations.get($)??0))};if(this._key!==null&&(t==="side"||this._key===s.key)&&(r===this._cover||i!==void 0&&this._scopeStops.includes(i)||this._targetsOverlap(this._targetKey(),this._target,r,e))){let v=this._target?.side==="both"&&l||i!==void 0&&this._remainingStops.includes(i);this._started&&v&&(i&&g(this._remainingStops),this._heldControl&&g(o)),f=this._pulseInFlight,v&&!this._heldControl&&d.size===0?this._repeatBlocked=!0:this._reset()}for(let v of[...this._pendingReleases.values()]){let $=v.target?.side==="both"&&v.target.deviceId===e?.deviceId&&(e?.side==="left"||e?.side==="right");t!=="side"&&$||t!=="side"&&v.motorKey!==s.key||!(v.cover===r||i!==void 0&&v.scopeGenerations.has(i)||this._targetsOverlap(v.targetKey,v.target,r,e))||(this._pendingReleases.delete(v.id),v.timer!==void 0&&this.timers.clearTimeout(v.timer),l&&v.target?.side==="both"&&[...v.scopeGenerations].every(([b,_])=>this._stopTargetGenerations.get(b)===_)&&g(o))}let y=this._key!==null?this._stop:null,x=()=>{for(let v of d)v!==y&&(this._stopTargetGenerations.get(v)??0)===h.get(v)&&this.actions.stopBed(v)};f?f.then(x,x):x()}stopAll(s,e,t,i=[]){let o=s??this._stop??void 0,r=this._key!==null&&this._started?{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0}:void 0,l=typeof t=="object"?t:void 0,d=typeof t=="string"?t:void 0,h=[...new Set([...Array.isArray(e)?e:o?[o]:this._scopeStops,...this._targetScope(l),...o?[o]:[]])],f=e===!0&&!l,g=d===void 0||d===this._key||o===this._cover,y=this._key!==null&&g&&(f||h.length===0||this._scopeStops.some(_=>h.includes(_))||this._targetsOverlap(this._targetKey(),this._target,o,l)),x=!1;s!==void 0&&(f?this._discardAllReleases():x=this._discardReleasesOverlapping(s,l)),x||=y&&this._started&&this._heldControl!==void 0&&this._target?.side==="both";let v=[...new Set([...y&&this._started?this._remainingStops:[],...x?i:[]])].filter(_=>!h.includes(_)&&_!==this._stop),$=y?this._pulseInFlight:void 0,b=new Map(v.map(_=>[_,this._stopTargetGenerations.get(_)??0]));if(y&&this._reset(),s===void 0){let _=this._flushAllReleases(),c=r?.stopEntityId??r?.cover;r&&(c===void 0||!_.has(c))?this._release(r):!r&&_.size===0&&this.actions.stopBed(o)}else this.actions.stopBed(s);if(v.length>0){let _=()=>{for(let c of v)(this._stopTargetGenerations.get(c)??0)===b.get(c)&&this.actions.stopBed(c)};$?$.then(_,_):_()}}abandon(){let s=this._key===null?null:{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0},e=this._started;this._reset();let t=new Set,i=o=>{o!==void 0&&t.add(o)};s&&e&&i(this._release(s));for(let o of[...this._pendingReleases.values()])i(this._runRelease(o));return[...t]}releaseOnFocusLoss(){this.abandon()}cancelForStopScope(s){let e=!1;for(let t of[...this._pendingReleases.values()])s.includes(t.targetKey)&&(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer),e=!0);return this._key!==null&&this._scopeStops.some(t=>s.includes(t))&&(this._reset(),e=!0),e}_reset(){this._startTimer!==void 0&&this.timers.clearTimeout(this._startTimer),this._startTimer=void 0,this._key=null,this._motor=null,this._scopeStops=[],this._remainingStops=[],this._keyboardKey=null,this._pulseInFlight=void 0,this._motorId=null,this._cover=null,this._stop=null,this._target=void 0,this._pointerId=null,this._repeatBlocked=!1,this._started=!1,this._heldControl=void 0,this._releaseButton=void 0,this._generation++}};function lt(n,s,e){let t=()=>{n.abandon()},i=()=>{s.visibilityState==="hidden"&&t()};return s.addEventListener("visibilitychange",i),e.addEventListener("pagehide",t),()=>{s.removeEventListener("visibilitychange",i),e.removeEventListener("pagehide",t)}}function ge(n,s,e,t,i){n.stopAll(s,e??(s?[s]:void 0),t??X(i,s),Pe(i,s))}var O="adjustable_bed";function ee(n){for(let s of["left","right","both"]){let e=`_${s}`;if(n.endsWith(e))return{key:n.slice(0,-e.length),side:s}}return{key:n}}var U=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],ct=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],Be=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_reading","preset_swing","preset_incline","preset_both_up","preset_yoga"],Dt={back:"back",foot:"feet",pillow:"pillow"},Nt=new Set(["elevate_both","starcode_m1x12_part_1","starcode_m1x12_part_2","starcode_m1x12_part_4","starcode_m1x12_part_8","starcode_m1x12_part_16"]),Wt=n=>n.split(".",1)[0],He=n=>n.translation_key??"";function Ft(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[],utilityStates:[]}}function E(n,s,e){let t=Ft();if(!s||!n?.entities)return t;let i=()=>t.lights.mood??={selects:[],numbers:[]},o=n.devices?.[s]?.parent_device_id||Object.values(n.devices??{}).some(_=>_.parent_device_id===s),r=Object.values(n.entities).filter(_=>_.device_id===s&&_.platform===O),l=!!e||!!o&&!r.some(_=>_.translation_key==="ble_connection"),d=new Map,h=_=>{let c=d.get(_);return c||(c=Nt.has(_)?{key:_,coverStopScope:"side"}:{key:_},d.set(_,c)),c},f=(_,c,he,K)=>{let k=h(c);k[he]=_;let z=n.states[_]?.attributes,G=z?.held_control,a=z?.hold_start_delay_ms,w=z?.hold_release_delay_ms;typeof G=="string"&&typeof a=="number"&&Number.isFinite(a)&&a>=0&&typeof w=="number"&&Number.isFinite(w)&&w>=0&&K&&(k.deviceId=K,k.holdEntityId=_,k.heldControls={...k.heldControls,[he]:{control:G,startDelayMs:a,releaseDelayMs:w}});let S=z?.paired_hold_motor;S==="back"||S==="legs"||S==="lumbar"?k.timedMove={deviceId:s,motor:S,...z?.paired_hold_side==="both"?{side:"both"}:{}}:(c==="back"||c==="legs"||c==="lumbar")&&typeof G=="string"&&(k.timedMove={deviceId:s,motor:c,...z?.bed_side==="both"?{side:"both"}:{}})},g=new Map,y=new Map,x=_=>{let c=y.get(_);return c||(c={slot:_},y.set(_,c)),c};for(let _ of r){if(_.hidden)continue;let c=_.entity_id,he=Wt(c),K=He(_);if(!K)continue;let k=ee(K),G=n.states[c]?.attributes.bed_side??n.states[c]?.attributes.side??k.side;if(e&&G!==e)continue;let a=l&&k.side===G?k.key:K,w;switch(he){case"cover":{let S=h(a);S.cover=c;let T=n.states[c]?.attributes,Ze=T?.held_control_up,Xe=T?.held_control_down,et=Me(n,c);if(et&&(S.releaseButton=et),(T?.held_stop_scope==="motor"||T?.held_stop_scope==="side")&&(S.coverStopScope=T.held_stop_scope),typeof Ze=="string"&&typeof Xe=="string"&&(typeof T?.hold_release_button_key!="string"||S.releaseButton)){(a==="back"||a==="legs"||a==="lumbar")&&(S.timedMove={deviceId:s,motor:a});let Q=T?.hold_start_delay_ms,Z=T?.hold_release_delay_ms;(T?.held_stop_scope==="motor"||T?.held_stop_scope==="side")&&_.device_id&&typeof Q=="number"&&Number.isFinite(Q)&&Q>=0&&typeof Z=="number"&&Number.isFinite(Z)&&Z>=0&&(S.deviceId=_.device_id,S.holdEntityId=c,S.heldControls={up:{control:Ze,startDelayMs:Q,releaseDelayMs:Z},down:{control:Xe,startDelayMs:Q,releaseDelayMs:Z}})}}break;case"sensor":if(a.startsWith("motomotion_")){(t.utilityStates??=[]).push(c);break}if(a==="eshine_okin_massage"){(t.massage.states??=[]).push(c);break}if(a==="eshine_okin_alarm"){t.utilityStates?.push(c);break}if(a.startsWith("goodvibe_")){t.utilityStates?.push(c);break}if(a==="cluster018_status"){t.utilityStates?.push(c);break}if(a.startsWith("doublesleep_")){/^doublesleep_(massage_|sonic_)/.test(a)?(t.massage.states??=[]).push(c):a==="doublesleep_light"?(t.lights.states??=[]).push(c):t.utilityStates?.push(c);break}if(/^adjustamattress_(massage_time|head_intensity|foot_intensity|wave)$/.test(a)){(t.massage.states??=[]).push(c);break}if(a.startsWith("adjustamattress_")){t.utilityStates?.push(c);break}a==="gmmotor_state"||a==="gmmotor_sleep_state"?t.utilityStates?.push(c):a.startsWith("starcode_m1x12_part_")&&a.endsWith("_position")?h(a.slice(0,-9)).position=c:a.endsWith("_angle")?h(a.slice(0,-6)).angle=c:a.startsWith("sleepys_app_position_")||a.startsWith("sleepys_app_field_")?t.utilityStates?.push(c):a.startsWith("reverie_")&&a.endsWith("_massage_intensity")?(t.massage.states??=[]).push(c):a==="sleepys_app_massage_timer_code"||a==="reverie_pairlink_massage_mode"||a==="reverie_pairlink_massage_timer"?(t.massage.states??=[]).push(c):a==="reverie_massage_wave"?(t.massage.states??=[]).push(c):a==="logicdata_air_pump_pressure"?t.firmness.push(c):a==="innova_massage_timer"||a==="glideaway_motion_massage_timer"||a==="bedsense_massage_timer"||a==="app_timer_status"?t.massage.timer=c:a==="bedsense_light_duration"?t.lights.state=c:/^bedsense_(head_bar|wave_bar|head_steps|foot_steps|wave_steps)$/.test(a)?(t.massage.states??=[]).push(c):a.startsWith("starcode_m1x12_light_")?(t.lights.states??=[]).push(c):/^starcode_m1x12_(massage_|sonic_|kneading_)/.test(a)?(t.massage.states??=[]).push(c):a.startsWith("starcode_m1x12_")&&t.utilityStates?.push(c);break;case"number":if(a.startsWith("motomotion_")){(t.utilityNumbers??=[]).push(c);break}if(a.startsWith("goodvibe_")){(t.utilityNumbers??=[]).push(c);break}if(a.startsWith("adjustamattress_")){(t.utilityNumbers??=[]).push(c);break}a.endsWith("_position")?h(a.slice(0,-9)).position=c:a==="reverie_body_tilt"?h("lumbar").position=c:!e&&k.side&&k.key.endsWith("_position")?h(`${k.key.slice(0,-9)}_${k.side}`).position=c:a.startsWith("massage_")&&a.endsWith("_intensity")||a==="reverie_wave_level"||a==="reverie_massage_wave"||a==="reverie_stk_head_wave"||a==="reverie_stk_global_massage"?t.massage.numbers.push(c):a==="reverie_pairlink_massage_timer"?t.massage.timer=c:a==="bf_cherish_intensity"||a==="bf_cherish_wave"?t.massage.numbers.push(c):a==="light_level"||a==="svane_intensity"||a==="starcode_brightness"||a==="starcode_m1x12_brightness"||a==="vmatbasic_floor_level"||a==="starcode_abm5_4_light_level"?t.lights.level=c:a==="vmatbasic_floor_minutes"?(t.lights.timerMinutes=c,t.lights.timerAppliesImmediately=!0):a==="vibradorm_app_floor_timer_minutes"?t.lights.timerMinutes=c:(w=a.match(/^richmat_mh_(back|foot|pillow)_angle$/))?h(Dt[w[1]]).position=c:a==="richmat_mh_light_timer"?t.lights.timer=c:a==="richmat_mh_light_timer_minutes"?(t.lights.timerMinutes=c,t.lights.timerAppliesImmediately=!0):a==="richmat_mh_head_massage_intensity"||a==="richmat_mh_foot_massage_intensity"?t.massage.numbers.push(c):a==="vibradorm_app_mood_speed"||a==="vmatbasic_mood_speed"||a==="vmatbasic_mood_brightness"?i().numbers.push(c):a==="vibradorm_app_massage_speed"||a==="sleeptracker_wave_minutes"?t.massage.numbers.push(c):a==="sleepys_app_color_code"?(t.lights.numbers??=[]).push(c):a.startsWith("sleepys_app_target_axis_")?(t.utilityNumbers??=[]).push(c):/^sleeptracker_(left|right)_level$/.test(a)||a==="fan_level"?t.climate.numbers.push(c):a.startsWith("sleep_number_setting")&&t.firmness.push(c);break;case"button":if(a==="motomotion_action"||a==="motomotion_release"){t.utility.push(c);break}if(a==="doublesleep_massage_action"){t.massage.buttons.push(c);break}if(a==="doublesleep_light_action"){(t.lights.buttons??=[]).push(c);break}if(a==="doublesleep_action"){t.utility.push(c);break}if(a==="adjustamattress_underbed_lighting"){(t.lights.buttons??=[]).push(c);break}if(/^adjustamattress_(head_strength_add|foot_strength_add|wave_add|massage_timer|timer\d+|query_massage.*)$/.test(a)){t.massage.buttons.push(c);break}if(a==="adjustamattress_m1"){g.set(a,c);break}if(a.startsWith("adjustamattress_")){t.utility.push(c);break}Be.includes(a)||a.startsWith("preset_")||a.startsWith("sleepys_app_preset_")?(w=a.match(/^preset_memory_(\d+)$/))?x(Number(w[1])).goto=c:g.set(a,c):(w=a.match(/^program_memory_(\d+)$/))?x(Number(w[1])).save=c:(w=a.match(/^sleepys_app_memory_(\d+)$/))?x(Number(w[1])).goto=c:a==="stop"||a==="stop_both"?t.stop=c:a==="connect"?t.connect=c:a==="disconnect"?t.disconnect=c:a==="bedsense_light"?(t.lights.buttons??=[]).push(c):a==="bedsense_massage"?t.massage.buttons.push(c):a==="bedsense_action"?t.utility.push(c):a==="sleeptracker_light_toggle"?t.lights.toggle=c:a==="sleeptracker_light_off"?(t.lights.buttons??=[]).push(c):/^sleeptracker_(massage_|wave_start|wind_down_|local_animation)/.test(a)?t.massage.buttons.push(c):a.startsWith("sleeptracker_")?t.utility.push(c):a.startsWith("sleepys_app_light_")||a.startsWith("sleepys_app_voice_brightness_")||a==="sleepys_app_rgb_action"?(t.lights.buttons??=[]).push(c):a.startsWith("sleepys_app_massage_")?t.massage.buttons.push(c):a==="toggle_light"?t.lights.toggle=c:a==="light_cycle"||a==="starcode_light_cycle"?t.lights.cycle=c:a==="vibradorm_app_mood_toggle"||a==="vmatbasic_mood_toggle"?i().toggle=c:a==="vmatbasic_mood_nightlight"?(i().buttons??=[]).push(c):a==="vmatbasic_floor_toggle"||a==="vmatbasic_floor_hold"?t.lights.toggle=c:a.startsWith("vmatbasic_massage_")?t.massage.buttons.push(c):a==="vibradorm_app_floor_timer_toggle"?t.lights.timerToggle=c:a==="remacro_led_brightness_save"?(t.lights.buttons??=[]).push(c):a==="starcode_abm5_4_light_plus"||a==="starcode_abm5_4_light_minus"||a==="starcode_abm5_4_light_on"||a==="starcode_abm5_4_light_off"?(t.lights.buttons??=[]).push(c):a==="starcode_abm5_4_massage_release"?t.massage.buttons.push(c):a.startsWith("starcode_abm5_4_")?t.utility.push(c):a==="okin_app_home"||a.startsWith("simmons_inclined")?g.set(a,c):a==="simmons_sync_clock"||a==="simmons_refresh_alarms"||a==="glideaway_motion_query_alarm"||a==="bf_query_alarm"?t.utility.push(c):a.startsWith("eshine_okin_massage_")?t.massage.buttons.push(c):a.startsWith("eshine_okin_")?t.utility.push(c):a.startsWith("eshine_massage_")?t.massage.buttons.push(c):a.startsWith("eshine_save_")?t.utility.push(c):a==="richmat_mh_massage"?t.massage.buttons.push(c):a==="richmat_mh_preset"?g.set(`${a}:${c}`,c):a==="hjbed_action"||a==="goodvibe_action"||a==="cluster018_action"||a==="cluster018_release"||a.startsWith("richmat_mh_")?t.utility.push(c):a.startsWith("adjustable_lumbar_wave_")||a==="adjustable_lumbar_massage_on"?t.massage.buttons.push(c):a.startsWith("adjustable_lumbar_")?t.utility.push(c):a==="logicdata_app_query_massage"?t.massage.buttons.push(c):a.startsWith("logicdata_air_pump_")?t.utility.push(c):/^comfort_enhancements_(head|foot|timer)_cycle$/.test(a)||a==="ore_comfort_massage_start"||a==="innova_massage_level"||a==="innova_massage_timer_hold"?t.massage.buttons.push(c):a==="ore_comfort_program_flat"||a==="ore_comfort_program_zero_g"?t.utility.push(c):a==="isleep_pattern"||a==="coolbase_head_massage"||a==="coolbase_foot_massage"||a==="coolbase_massage_mode"?t.massage.buttons.push(c):a==="comfort_enhancements_quiet_sleep"?g.set(a,c):a==="restonic_zzz"||a.startsWith("coolbase_")?t.utility.push(c):a==="vibradorm_app_massage_automatic"||a==="vibradorm_app_massage_individual"||a.startsWith("starcode_m1x12_hold_")?t.massage.buttons.push(c):(w=a.match(/^(starcode_m1x12_part_\d+)_(up|down)$/))?f(c,w[1],w[2],_.device_id):a==="sync_positions"||a==="child_lock_toggle"||a==="auxiliary_action"||a==="remote_action"||a==="solace_music_toggle"||a==="solace_music_off"||a==="wake_controller"||a==="octo_all_down"||a==="reset_defaults"||a==="factory_reset"||a==="isleep_all_up"||a==="isleep_all_down"||a==="vibradorm_app_all_up"||a==="vibradorm_app_all_down"||a==="vibradorm_app_sync"||a==="vibradorm_app_refresh_info"||a==="vmatbasic_all_up"||a==="vmatbasic_all_down"||a==="vmatbasic_refresh_info"||a.startsWith("starcode_save_")||a==="starcode_reset"||a==="starcode_query"||a==="starcode_light_mode"||a.startsWith("starcode_m1x12_")?t.utility.push(c):a.startsWith("massage_")?t.massage.buttons.push(c):a.startsWith("sleepys_app_")||a==="casper_base_action"||a==="hush_base_action"?t.utility.push(c):a==="bf_cherish_both_up"||a==="bf_cherish_both_down"?f(c,"back_legs",a.endsWith("_up")?"up":"down",_.device_id):(w=a.match(/^(.+)_(up|down)$/))&&f(c,w[1],w[2],_.device_id);break;case"switch":a==="under_bed_lights"?t.lights.switch=c:a==="synchro_mode"?t.synchro=c:(a==="linak_automatic_drive"||a==="automatic_light"||a==="remote_control_lock")&&t.utility.push(c);break;case"light":t.lights.light=c;break;case"binary_sensor":if(a.startsWith("doublesleep_")){t.utilityStates?.push(c);break}if(a.startsWith("adjustamattress_")){t.utilityStates?.push(c);break}a==="ble_connection"?t.connectivity=c:a==="memory_save_response_observed"?t.utilityStates?.push(c):a==="sleeptracker_wind_down_running"?(t.massage.states??=[]).push(c):a==="reverie_pairlink_low_battery"?t.utility.push(c):a==="under_bed_lights"||a==="adjustable_lite_light"||a==="innova_light"||a==="sleeptracker_light_on"||a==="starcode_m1x12_light_on"?t.lights.state=c:/^starcode_m1x12_(massage_|sonic_|kneading_)/.test(a)?(t.massage.states??=[]).push(c):a.startsWith("starcode_m1x12_")?t.utilityStates?.push(c):a.startsWith("bed_presence")&&t.presence.push(c);break;case"select":if(a.startsWith("motomotion_")){(t.utilitySelects??=[]).push(c);break}if(a==="doublesleep_child_lock"){(t.utilitySelects??=[]).push(c);break}if(/^adjustamattress_(head|foot|wave)_selector$/.test(a)){(t.massage.selects??=[]).push(c);break}if(a.startsWith("adjustamattress_")){(t.utilitySelects??=[]).push(c);break}a.startsWith("cluster018_")||a==="goodvibe_massage_timer"||a==="goodvibe_light_duration"||a==="hjbed_layout"||a==="motion_bed_active_module"||a.startsWith("okin_app_")?(t.utilitySelects??=[]).push(c):a==="reverie_stk_side"?(t.utilitySelects??=[]).push(c):a==="sleepys_app_massage_timer_code"||a==="reverie_pairlink_massage_mode"||a==="reverie_pairlink_massage_rhythm"?(t.massage.selects??=[]).push(c):a==="light_timer"?t.lights.timer=c:a==="remacro_control_side"||a==="goodvibe_side"?t.controlSide=c:a==="starcode_color"||a==="vibradorm_app_mood_palette"||a==="vibradorm_app_mood_effect"||a==="vmatbasic_mood_palette"||a==="vmatbasic_mood_effect"?i().selects.push(c):a==="sleeptracker_wave_frequency"||/^sleeptracker_massage_(head_level|foot_level|pattern_option)$/.test(a)?(t.massage.selects??=[]).push(c):/^sleeptracker_(left|right)_(mode|curve)$/.test(a)?t.climate.selects.push(c):a==="vibradorm_app_massage_wave"?(t.massage.selects??=[]).push(c):a==="richmat_mh_motor_mode"||a==="richmat_mh_snore"?(t.utilitySelects??=[]).push(c):a.startsWith("richmat_mh_waist_")?(t.massage.selects??=[]).push(c):a==="massage_timer"||a==="starcode_abm5_4_massage_timer"||a==="ore_comfort_massage_timer"?t.massage.timer=c:/thermal|footwarming|foundation/.test(a)&&t.climate.selects.push(c);break;case"climate":t.climate.entities.push(c);break}}let v=[...d.keys()],$=[...ct.filter(_=>d.has(_)),...v.filter(_=>!ct.includes(_)).sort()];t.motors=$.map(_=>d.get(_)).filter(_=>_.cover||_.up||_.down||_.angle||_.position);let b=[...g.keys()];return t.presets=[...Be.filter(_=>g.has(_)),...b.filter(_=>!Be.includes(_)).sort()].map(_=>g.get(_)),t.memory=[...y.values()].filter(_=>_.goto||_.save).sort((_,c)=>_.slot-c.slot),t}function me(n,s){return!s||!n?.entities?!1:Object.values(n.entities).some(e=>e.device_id===s&&e.platform===O&&(n.states[e.entity_id]?.attributes.bed_side==="both"||ee(He(e)).side==="both"))}function te(n,s){if(!s||!n?.devices)return[];let e=i=>{let o=n.devices[i];return(o?.name_by_user??o?.name??i).toLowerCase()},t=i=>{for(let o of Object.values(n.entities??{})){if(o.device_id!==i||o.platform!=="adjustable_bed")continue;let r=n.states[o.entity_id]?.attributes.bed_side??ee(He(o)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(n.devices).filter(i=>(i.parent_device_id??i.via_device_id)===s).map(i=>i.id).sort((i,o)=>t(i)-t(o)||e(i).localeCompare(e(o)))}function _e(n,s){if(!s||!n?.devices)return s;let e=n.devices[s]?.parent_device_id??n.devices[s]?.via_device_id;return e&&n.devices[e]&&te(n,e).length?e:s}function P(n){let s=n.lights;return n.motors.length===0&&!n.synchro&&!n.controlSide&&n.firmness.length===0&&n.presets.length===0&&n.memory.length===0&&!n.stop&&!n.connect&&!n.disconnect&&!n.connectivity&&!I(s)&&!s.state&&n.massage.buttons.length===0&&n.massage.numbers.length===0&&!n.massage.selects?.length&&!n.massage.states?.length&&!n.massage.timer&&n.climate.entities.length===0&&n.climate.selects.length===0&&n.climate.numbers.length===0&&n.utility.length===0&&!n.utilityNumbers?.length&&!n.utilitySelects?.length&&!n.utilityStates?.length}function I(n){return!!(n.light||n.switch||n.level||n.toggle||n.numbers?.length||n.buttons?.length||n.states?.length||n.cycle||n.timer||n.timerMinutes||n.timerToggle||n.mood?.toggle||n.mood?.selects.length||n.mood?.numbers.length||n.mood?.buttons?.length)}var ze="adjustable-bed-card",dt={type:ze,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(n,s)=>{let e=n.entities[s];return e?.platform!==O||!e.device_id?null:{config:{type:`custom:${ze}`,device_id:e.device_id}}}};function Kt(n){let s=n.customCards??=[],e=s.findIndex(t=>t.type===ze);e===-1?s.push(dt):s[e]=dt}function fe(n,s,e=window){let t=e.customElements;t.get(n)||t.define(n,s),t.whenDefined("home-assistant").then(()=>{let i=e.customElements;i!==t&&!i.get(n)&&i.define(n,s)})}typeof window<"u"&&Kt(window);var ve=globalThis,be=ve.ShadowRoot&&(ve.ShadyCSS===void 0||ve.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Oe=Symbol(),ht=new WeakMap,ie=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==Oe)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(be&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=ht.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&ht.set(e,s))}return s}toString(){return this.cssText}},pt=n=>new ie(typeof n=="string"?n:n+"",void 0,Oe),se=(n,...s)=>{let e=n.length===1?n[0]:s.reduce((t,i,o)=>t+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[o+1],n[0]);return new ie(e,n,Oe)},ut=(n,s)=>{if(be)n.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=ve.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,n.appendChild(t)}},Le=be?n=>n:n=>n instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return pt(e)})(n):n;var{is:Gt,defineProperty:Ut,getOwnPropertyDescriptor:It,getOwnPropertyNames:qt,getOwnPropertySymbols:Vt,getPrototypeOf:Yt}=Object,ye=globalThis,gt=ye.trustedTypes,Jt=gt?gt.emptyScript:"",Qt=ye.reactiveElementPolyfillSupport,oe=(n,s)=>n,ne={toAttribute(n,s){switch(s){case Boolean:n=n?Jt:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,s){let e=n;switch(s){case Boolean:e=n!==null;break;case Number:e=n===null?null:Number(n);break;case Object:case Array:try{e=JSON.parse(n)}catch{e=null}}return e}},xe=(n,s)=>!Gt(n,s),mt={attribute:!0,type:String,converter:ne,reflect:!1,useDefault:!1,hasChanged:xe};Symbol.metadata??=Symbol("metadata"),ye.litPropertyMetadata??=new WeakMap;var R=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=mt){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&Ut(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:o}=It(this.prototype,s)??{get(){return this[e]},set(r){this[e]=r}};return{get:i,set(r){let l=i?.call(this);o?.call(this,r),this.requestUpdate(s,l,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??mt}static _$Ei(){if(this.hasOwnProperty(oe("elementProperties")))return;let s=Yt(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(oe("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(oe("properties"))){let e=this.properties,t=[...qt(e),...Vt(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(Le(i))}else s!==void 0&&e.push(Le(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return ut(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let o=(t.converter?.toAttribute!==void 0?t.converter:ne).toAttribute(e,t.type);this._$Em=s,o==null?this.removeAttribute(i):this.setAttribute(i,o),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let o=t.getPropertyOptions(i),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:ne;this._$Em=i;let l=r.fromAttribute(e,o.type);this[i]=l??this._$Ej?.get(i)??l,this._$Em=null}}requestUpdate(s,e,t,i=!1,o){if(s!==void 0){let r=this.constructor;if(i===!1&&(o=this[s]),t??=r.getPropertyOptions(s),!((t.hasChanged??xe)(o,e)||t.useDefault&&t.reflect&&o===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:o},r){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??e??this[s]),o!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,o]of this._$Ep)this[i]=o;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,o]of t){let{wrapped:r}=o,l=this[i];r!==!0||this._$AL.has(i)||l===void 0||this.C(i,void 0,o,l)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};R.elementStyles=[],R.shadowRootOptions={mode:"open"},R[oe("elementProperties")]=new Map,R[oe("finalized")]=new Map,Qt?.({ReactiveElement:R}),(ye.reactiveElementVersions??=[]).push("2.1.2");var Ge=globalThis,_t=n=>n,$e=Ge.trustedTypes,ft=$e?$e.createPolicy("lit-html",{createHTML:n=>n}):void 0,wt="$lit$",B=`lit$${Math.random().toFixed(9).slice(2)}$`,kt="?"+B,Zt=`<${kt}>`,D=document,ae=()=>D.createComment(""),le=n=>n===null||typeof n!="object"&&typeof n!="function",Ue=Array.isArray,Xt=n=>Ue(n)||typeof n?.[Symbol.iterator]=="function",je=`[ \t
\f\r]`,re=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,vt=/-->/g,bt=/>/g,L=RegExp(`>|${je}(?:([^\\s"'>=/]+)(${je}*=${je}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),yt=/'/g,xt=/"/g,St=/^(?:script|style|textarea|title)$/i,Ie=n=>(s,...e)=>({_$litType$:n,strings:s,values:e}),u=Ie(1),we=Ie(2),$i=Ie(3),N=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),$t=new WeakMap,j=D.createTreeWalker(D,129);function Et(n,s){if(!Ue(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return ft!==void 0?ft.createHTML(s):s}var ei=(n,s)=>{let e=n.length-1,t=[],i,o=s===2?"<svg>":s===3?"<math>":"",r=re;for(let l=0;l<e;l++){let d=n[l],h,f,g=-1,y=0;for(;y<d.length&&(r.lastIndex=y,f=r.exec(d),f!==null);)y=r.lastIndex,r===re?f[1]==="!--"?r=vt:f[1]!==void 0?r=bt:f[2]!==void 0?(St.test(f[2])&&(i=RegExp("</"+f[2],"g")),r=L):f[3]!==void 0&&(r=L):r===L?f[0]===">"?(r=i??re,g=-1):f[1]===void 0?g=-2:(g=r.lastIndex-f[2].length,h=f[1],r=f[3]===void 0?L:f[3]==='"'?xt:yt):r===xt||r===yt?r=L:r===vt||r===bt?r=re:(r=L,i=void 0);let x=r===L&&n[l+1].startsWith("/>")?" ":"";o+=r===re?d+Zt:g>=0?(t.push(h),d.slice(0,g)+wt+d.slice(g)+B+x):d+B+(g===-2?l:x)}return[Et(n,o+(n[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},ce=class n{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let o=0,r=0,l=s.length-1,d=this.parts,[h,f]=ei(s,e);if(this.el=n.createElement(h,t),j.currentNode=this.el.content,e===2||e===3){let g=this.el.content.firstChild;g.replaceWith(...g.childNodes)}for(;(i=j.nextNode())!==null&&d.length<l;){if(i.nodeType===1){if(i.hasAttributes())for(let g of i.getAttributeNames())if(g.endsWith(wt)){let y=f[r++],x=i.getAttribute(g).split(B),v=/([.?@])?(.*)/.exec(y);d.push({type:1,index:o,name:v[2],strings:x,ctor:v[1]==="."?Ne:v[1]==="?"?We:v[1]==="@"?Fe:V}),i.removeAttribute(g)}else g.startsWith(B)&&(d.push({type:6,index:o}),i.removeAttribute(g));if(St.test(i.tagName)){let g=i.textContent.split(B),y=g.length-1;if(y>0){i.textContent=$e?$e.emptyScript:"";for(let x=0;x<y;x++)i.append(g[x],ae()),j.nextNode(),d.push({type:2,index:++o});i.append(g[y],ae())}}}else if(i.nodeType===8)if(i.data===kt)d.push({type:2,index:o});else{let g=-1;for(;(g=i.data.indexOf(B,g+1))!==-1;)d.push({type:7,index:o}),g+=B.length-1}o++}}static createElement(s,e){let t=D.createElement("template");return t.innerHTML=s,t}};function q(n,s,e=n,t){if(s===N)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,o=le(s)?void 0:s._$litDirective$;return i?.constructor!==o&&(i?._$AO?.(!1),o===void 0?i=void 0:(i=new o(n),i._$AT(n,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=q(n,i._$AS(n,s.values),i,t)),s}var De=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??D).importNode(e,!0);j.currentNode=i;let o=j.nextNode(),r=0,l=0,d=t[0];for(;d!==void 0;){if(r===d.index){let h;d.type===2?h=new de(o,o.nextSibling,this,s):d.type===1?h=new d.ctor(o,d.name,d.strings,this,s):d.type===6&&(h=new Ke(o,this,s)),this._$AV.push(h),d=t[++l]}r!==d?.index&&(o=j.nextNode(),r++)}return j.currentNode=D,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},de=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=q(this,s,e),le(s)?s===p||s==null||s===""?(this._$AH!==p&&this._$AR(),this._$AH=p):s!==this._$AH&&s!==N&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):Xt(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==p&&le(this._$AH)?this._$AA.nextSibling.data=s:this.T(D.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=ce.createElement(Et(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let o=new De(i,this),r=o.u(this.options);o.p(e),this.T(r),this._$AH=o}}_$AC(s){let e=$t.get(s.strings);return e===void 0&&$t.set(s.strings,e=new ce(s)),e}k(s){Ue(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let o of s)i===e.length?e.push(t=new n(this.O(ae()),this.O(ae()),this,this.options)):t=e[i],t._$AI(o),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=_t(s).nextSibling;_t(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},V=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,o){this.type=1,this._$AH=p,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=o,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=p}_$AI(s,e=this,t,i){let o=this.strings,r=!1;if(o===void 0)s=q(this,s,e,0),r=!le(s)||s!==this._$AH&&s!==N,r&&(this._$AH=s);else{let l=s,d,h;for(s=o[0],d=0;d<o.length-1;d++)h=q(this,l[t+d],e,d),h===N&&(h=this._$AH[d]),r||=!le(h)||h!==this._$AH[d],h===p?s=p:s!==p&&(s+=(h??"")+o[d+1]),this._$AH[d]=h}r&&!i&&this.j(s)}j(s){s===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},Ne=class extends V{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===p?void 0:s}},We=class extends V{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==p)}},Fe=class extends V{constructor(s,e,t,i,o){super(s,e,t,i,o),this.type=5}_$AI(s,e=this){if((s=q(this,s,e,0)??p)===N)return;let t=this._$AH,i=s===p&&t!==p||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,o=s!==p&&(t===p||i);i&&this.element.removeEventListener(this.name,this,t),o&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},Ke=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){q(this,s)}};var ti=Ge.litHtmlPolyfillSupport;ti?.(ce,de),(Ge.litHtmlVersions??=[]).push("3.3.3");var Tt=(n,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let o=e?.renderBefore??null;t._$litPart$=i=new de(s.insertBefore(ae(),o),o,void 0,e??{})}return i._$AI(n),i};var qe=globalThis,A=class extends R{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=Tt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return N}};A._$litElement$=!0,A.finalized=!0,qe.litElementHydrateSupport?.({LitElement:A});var ii=qe.litElementPolyfillSupport;ii?.({LitElement:A});(qe.litElementVersions??=[]).push("4.2.2");var si={attribute:!0,type:String,converter:ne,reflect:!1,hasChanged:xe},oi=(n=si,s,e)=>{let{kind:t,metadata:i}=e,o=globalThis.litPropertyMetadata.get(i);if(o===void 0&&globalThis.litPropertyMetadata.set(i,o=new Map),t==="setter"&&((n=Object.create(n)).wrapped=!0),o.set(e.name,n),t==="accessor"){let{name:r}=e;return{set(l){let d=s.get.call(this);s.set.call(this,l),this.requestUpdate(r,d,n,!0,l)},init(l){return l!==void 0&&this.C(r,void 0,n,l),l}}}if(t==="setter"){let{name:r}=e;return function(l){let d=this[r];s.call(this,l),this.requestUpdate(r,d,n,!0,l)}}throw Error("Unsupported decorator location: "+t)};function Y(n){return(s,e)=>typeof e=="object"?oi(n,s,e):((t,i,o)=>{let r=i.hasOwnProperty(o);return i.constructor.createProperty(o,t),r?Object.getOwnPropertyDescriptor(i,o):void 0})(n,s,e)}function H(n){return Y({...n,state:!0,attribute:!1})}var W=n=>Math.max(0,Math.min(75,n));function Ve(n,s="theme"){let e=W(n.upper.angle??0),t=W(n.lower.angle??0),i=`rotate(${e} 150 70)`,o=`rotate(${-t} 150 70)`,r=l=>l.angle===void 0?"":`${l.label?`${l.label} `:""}${Math.round(W(l.angle))}\xB0`;return we`
    <svg
      class="bed-graphic bed-graphic-${s} ${n.moving?"is-moving":""}"
      viewBox="0 -44 300 180"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abSingleMattress" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-mattress-stop" offset="0%" stop-opacity="1" />
          <stop class="bed-mattress-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
        <linearGradient id="abSingleFrame" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-frame-stop" offset="0%" stop-opacity="0.88" />
          <stop class="bed-frame-stop" offset="100%" stop-opacity="0.58" />
        </linearGradient>
      </defs>

      <!-- frame + legs -->
      <rect class="bed-frame" x="30" y="78" width="240" height="8" rx="4" fill="url(#abSingleFrame)" />
      <rect class="bed-frame" x="34" y="83" width="6" height="24" rx="3" fill="url(#abSingleFrame)" />
      <rect class="bed-frame" x="260" y="83" width="6" height="24" rx="3" fill="url(#abSingleFrame)" />

      <g class="bed-side-layer" fill="url(#abSingleMattress)">
        <!-- foot panel (right of hinge) -->
        <g class="bed-panel" transform=${o}>
          <rect class="bed-surface" x="150" y="58" width="108" height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel" transform=${i}>
          <rect class="bed-surface" x="42" y="58" width="108" height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
      </g>

      <text x="86" y="128" text-anchor="middle" class="bed-graphic-label">${r(n.upper)}</text>
      <text x="214" y="128" text-anchor="middle" class="bed-graphic-label">${r(n.lower)}</text>
    </svg>
  `}function Ye(n){let s=W(n.left.upper.angle??0),e=W(n.left.lower.angle??0),t=W(n.right.upper.angle??0),i=W(n.right.lower.angle??0),o=(r,l,d,h)=>we`
    <g
      class="dual-bed-side dual-bed-side-${r} ${h?"is-moving":""}"
      fill=${`url(#abDual${r==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${`rotate(${-d} 150 70)`}
      >
        <rect class="dual-bed-surface" x="150" y="58" width="108" height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${`rotate(${l} 150 70)`}
      >
        <rect class="dual-bed-surface" x="42" y="58" width="108" height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
    </g>
  `;return we`
    <svg
      class="bed-graphic dual-bed-graphic ${n.left.moving||n.right.moving?"is-moving":""}"
      viewBox="0 -44 300 160"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abDualFrame" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-frame-stop" offset="0%" stop-opacity="0.88" />
          <stop class="bed-frame-stop" offset="100%" stop-opacity="0.58" />
        </linearGradient>
        <linearGradient id="abDualLeft" x1="0" y1="0" x2="0" y2="1">
          <stop class="dual-bed-left-stop" offset="0%" stop-opacity="1" />
          <stop class="dual-bed-left-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
        <linearGradient id="abDualRight" x1="0" y1="0" x2="0" y2="1">
          <stop class="dual-bed-right-stop" offset="0%" stop-opacity="1" />
          <stop class="dual-bed-right-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
      </defs>
      <rect class="dual-bed-frame" x="30" y="78" width="240" height="8" rx="4" fill="url(#abDualFrame)" />
      <rect class="dual-bed-frame" x="34" y="83" width="6" height="24" rx="3" fill="url(#abDualFrame)" />
      <rect class="dual-bed-frame" x="260" y="83" width="6" height="24" rx="3" fill="url(#abDualFrame)" />
      ${o("right",t,i,n.right.moving)}
      ${o("left",s,e,n.left.moving)}
    </svg>
  `}function Je(n){let s=n.find(t=>t.key==="back"||t.key==="head"),e=n.find(t=>t.key==="legs"||t.key==="feet");return s&&e?{upper:s,lower:e}:void 0}function Ct(n,s){let e=n.motors.filter(t=>{let i=t.angle??t.position;return s.states[i??""]?.attributes.unit_of_measurement==="\xB0"});return Je(e)!==void 0}var At={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both"};var Mt={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge"};var F={en:At,nb:Mt};function ai(n){let s=(n?.locale?.language||n?.language||"en").toLowerCase(),e=s.split("-")[0];return F[s]?F[s]:F[e]?F[e]:e==="nn"||e==="no"?F.nb:F.en}function m(n,s,e){let i=ai(n)[s]??F.en[s]??s;if(e)for(let[o,r]of Object.entries(e))i=i.replace(`{${o}}`,r);return i}var Rt=["glance","quick","controls"];function Pt(n,s){let e={...n,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:s==="glance"?"names":"angles",show_side_selector:!0,show_motors:s==="controls",show_lighting:!1,show_connection:!1,animate:!0};return s==="glance"?e.compact_actions=[]:delete e.compact_actions,e}function Qe(n,s){return[...s.presets,...s.memory.flatMap(e=>e.goto?[e.goto]:[])].flatMap(e=>{let t=n.entities[e]?.translation_key;return t?[{key:ee(t).key,entityId:e}]:[]})}function Se(n,s,e){let t=Qe(n,s);if(e){let r=new Map(t.map(l=>[l.key,l]));return[...new Set(e)].flatMap(l=>{let d=r.get(l);return d?[d]:[]})}let i=t.find(r=>r.key==="preset_flat"),o=t.find(r=>r.key.startsWith("preset_memory_"))??t.find(r=>r!==i);return[i,o].filter(r=>r!==void 0)}function Ee(n){return n.stop?[n.stop]:n.motors.flatMap(s=>s.cover?[s.cover]:[])}function Te(n){if(!(!n||!n.startsWith("/")||/^\/[/\\]/.test(n)||/[\\\s]/.test(n)))return n}function Ce(n,s){let e=_e(n,s),t=te(n,e);return e&&t.length?[{key:"both",label:m(n,"card.both_sides"),bed:E(n,e)},...t.map(i=>({key:i,label:n.devices[i]?.name_by_user??n.devices[i]?.name??i,bed:E(n,i)}))]:me(n,s)?["both","left","right"].map(i=>({key:i,label:m(n,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:E(n,s,i)})):[{key:"both",label:m(n,"card.both_sides"),bed:E(n,s)}]}var Bt="4.3.0";function Ht(n,s){return{graphic:Ct(n,s),motors:n.motors.some(e=>e.cover||e.up||e.down)||!!n.stop||!!n.synchro,firmness:n.firmness.length>0,presets:n.presets.length>0,memory:n.memory.length>0,lighting:I(n.lights)||!!n.lights.state,massage:n.massage.buttons.length>0||n.massage.numbers.length>0||!!n.massage.states?.length||!!n.massage.selects?.length||!!n.massage.timer,utility:n.utility.length>0,climate:n.climate.entities.length>0||n.climate.selects.length>0||n.climate.numbers.length>0,connection:!!(n.connect||n.disconnect)}}var li="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",ci="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",di=(n,s)=>n.length===s.length&&n.every((e,t)=>e===s[t]),J=class extends A{constructor(){super(...arguments);this._computeLabel=e=>m(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!this.hass||!e)return;let t=Ce(this.hass,e).map(r=>r.bed),i=t[0];if(!i)return;let o=new Map;for(let r of t)for(let l of r.memory){let d=o.get(l.slot);o.set(l.slot,{slot:l.slot,goto:d?.goto??l.goto,save:d?.save??l.save})}return{...i,memory:[...o.values()].sort((r,l)=>r.slot-l.slot)}}_presentKeys(e){let t=this.hass?Ce(this.hass,this._config?.device_id).map(i=>i.bed):[e];return U.filter(i=>t.some(o=>Ht(o,this.hass)[i]))}_orderedKeys(e){let t=this._presentKeys(e),o=(this._config?.section_order??[]).filter(l=>t.includes(l)),r=t.filter(l=>!o.includes(l));return[...o,...r]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=t&&this.hass?.states[t]?.attributes.friendly_name||`Memory ${e.slot}`,o=t&&this.hass?.entities[t]?.device_id,r=o?this.hass?.devices[o]:void 0,l=r?.name_by_user||r?.name;return l&&i.startsWith(`${l} `)?i.slice(l.length+1):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id!==t.device_id&&delete i.default_target,i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let o=this._orderedKeys(e),r=o.indexOf(t),l=r+i;if(r<0||l<0||l>=o.length)return;[o[r],o[l]]=[o[l],o[r]];let d=this._cfg;di(o,this._presentKeys(e))?delete d.section_order:d.section_order=o,this._emit(d)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let o=this._memorySlots(e),r=this._config?.memory_slots,l=r&&r.length?r.map(Number):[...o];i?l.includes(t)||l.push(t):l=l.filter(h=>h!==t),l.sort((h,f)=>h-f);let d=this._cfg;l.length===o.length?delete d.memory_slots:d.memory_slots=l,this._emit(d)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?u`
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.sections")}</div>
        ${t.map((i,o)=>{let r=this._config?.[`show_${i}`]!==!1;return u`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${o===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${m(this.hass,"editor.move_up")}
                  aria-label=${m(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${li}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${o===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${m(this.hass,"editor.move_down")}
                  aria-label=${m(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${ci}></path></svg>
                </button>
              </div>
              <span class="label">${m(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${r}
                @change=${l=>this._toggleSection(i,l.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:p}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return p;let i=e.memory.some(r=>r.save),o=e.memory.length>1;return!i&&!o?p:u`
      <div class="group">
        <div class="group-title">
          ${m(this.hass,"editor.memory_group")}
        </div>
        ${i?u`<div class="row">
                <span class="label">${m(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:p}
        ${o?u`<div class="sub">
                <div class="sub-label">
                  ${m(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(r=>u`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${l=>this._toggleSlot(e,r.slot,l.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(r)}</span>
                    </label>
                  `)}
              </div>`:p}
      </div>
    `}_setOption(e,t){this._emit({...this._cfg,[e]:t})}_compactToggle(e,t){return u`<div class="row"><span class="label">${m(this.hass,e==="show_connection"?"editor.compact_connection":`editor.${e}`)}</span>
      <ha-switch .checked=${this._config?.[e]??t}
        @change=${i=>this._setOption(e,i.target.checked)}></ha-switch>
    </div>`}_compactGroup(){let e=this._config,t=Ce(this.hass,e.device_id),i=t.find(d=>d.key===(e.default_target??"both")),o=t.flatMap(d=>Qe(this.hass,d.bed)).filter((d,h,f)=>f.findIndex(g=>g.key===d.key)===h),r=e.compact_actions??(i?Se(this.hass,i.bed).map(d=>d.key):[]),l=[...r.filter(d=>o.some(h=>h.key===d)),...o.map(d=>d.key).filter(d=>!r.includes(d))];return u`
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        <label class="row"><span class="label">${m(this.hass,"editor.compact_labels")}</span>
          <select .value=${e.compact_labels??"angles"}
            @change=${d=>this._setOption("compact_labels",d.target.value)}>
            ${["angles","names","none"].map(d=>u`
              <option value=${d}>${m(this.hass,`editor.labels_${d}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        <label class="row path-row"><span class="label">${m(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${e.navigation_path??""} placeholder="/dashboard/bed"
            @change=${d=>this._setOption("navigation_path",d.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.compact_controls")}</div>
        ${t.length>1||!i?u`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${m(this.hass,"editor.default_target")}</span>
            <select .value=${e.default_target??"both"}
              @change=${d=>this._setOption("default_target",d.target.value)}>
              ${i?p:u`<option value=${e.default_target}>${m(this.hass,"compact.target_missing")}</option>`}
              ${t.map(d=>u`<option value=${d.key}>${d.label}</option>`)}
            </select>
          </label>`:p}
        ${this._compactToggle("show_motors",!1)}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${m(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${m(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${m(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${m(this.hass,"editor.labels_none")}</button>
        </div>
        ${l.map(d=>{let h=o.find(v=>v.key===d),f=r.includes(d),g=r.indexOf(d),y=v=>{let $=[...r];[$[g],$[g+v]]=[$[g+v],$[g]],this._setOption("compact_actions",$)},x=this.hass.states[h.entityId];return u`<div class="row">
            <ha-checkbox .checked=${f} @change=${v=>this._setOption("compact_actions",v.target.checked?[...r,d]:r.filter($=>$!==d))}></ha-checkbox>
            <span class="label">${x?.attributes.friendly_name??d}</span>
            <button class="icon-btn" ?disabled=${!f||g===0}
              aria-label=${m(this.hass,"editor.move_up")} @click=${()=>y(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!f||g===r.length-1}
              aria-label=${m(this.hass,"editor.move_down")} @click=${()=>y(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return u`<div class="group">
      <label class="row"><span class="label">${m(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${e=>this._setOption("layout",e.target.value)}>
          <option value="full">${m(this.hass,"editor.layout_full")}</option>
          <option value="compact">${m(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${m(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${Rt.map(e=>u`
        <button @click=${()=>this._emit({...Pt(this._config,e)})}>
          ${m(this.hass,`editor.recipe_${e}`)}
        </button>`)}</div>
    </div>`}render(){if(!this.hass||!this._config)return p;let e=this._bed();return u`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():u`
        ${e?this._sectionsGroup(e):p}
        ${e?this._memoryGroup(e):p}
      `}
    `}};J.styles=se`
    select, input { min-width: 0; max-width: 60%; box-sizing: border-box;
      background: var(--card-background-color); color: var(--primary-text-color);
      border: 1px solid var(--divider-color); border-radius: 6px; padding: 8px; font: inherit; }
    .path-row { flex-wrap: wrap; }
    .path-row input { flex: 1; min-width: 180px; max-width: 100%; }
    .recipes { display: flex; gap: 6px; flex-wrap: wrap; }
    .recipes button { background: var(--secondary-background-color); color: var(--primary-text-color);
      border: 1px solid var(--divider-color); border-radius: 7px; min-height: 44px;
      padding: 8px 12px; cursor: pointer; font: inherit; font-size: .85rem; }
    .hint { color: var(--secondary-text-color); font-size: .8rem; line-height: 1.4; }
    button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

    .group {
      margin-top: 16px;
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      padding: 8px 12px 12px;
    }
    .group-title {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
      padding: 4px 0 8px;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 40px;
    }
    .label {
      flex: 1;
      color: var(--primary-text-color);
    }
    .reorder {
      display: inline-flex;
      gap: 2px;
    }
    .icon-btn {
      border: none;
      background: none;
      color: var(--secondary-text-color);
      cursor: pointer;
      width: 28px;
      height: 28px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
    }
    .icon-btn svg {
      width: 20px;
      height: 20px;
      fill: currentColor;
    }
    .icon-btn:hover:not([disabled]) {
      color: var(--primary-color);
      background: var(--secondary-background-color);
    }
    .icon-btn[disabled] {
      opacity: 0.3;
      cursor: default;
    }
    .sub {
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--divider-color);
    }
    .sub-label {
      font-size: 0.8rem;
      color: var(--secondary-text-color);
      padding-bottom: 4px;
    }
    .check-row {
      display: flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
    }
  `,C([Y({attribute:!1})],J.prototype,"hass",2),C([H()],J.prototype,"_config",2);fe("adjustable-bed-card-editor",J);var hi=new Set(["back","legs","head","feet"]),M=class extends A{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._watched=[];this._compactStopTargets=new Map;this._hold=new ue({pulse:(e,t)=>Re(this.hass,e,t),holdControl:(e,t)=>st(this.hass,e,t),stopCover:(e,t)=>this._stopCompactTarget(e,t??e),stopBed:e=>{e&&this._stopCompactTarget(e)}});this._focusLossCleanup=null;this._windowPointerEnd=e=>{this._hold.endActiveFromPointer(e.pointerId,e.type==="pointercancel"||e.button===0)};this._windowKeyUp=e=>{(e.key==="Enter"||e.key===" ")&&this._hold.endKeyboard(void 0,void 0,e.key)};this._navigate=()=>{let e=Te(this._config?.navigation_path);e&&(this._hold.abandon(),history.pushState(null,"",e),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))}}connectedCallback(){super.connectedCallback(),this._removeHoldLifecycle=lt(this._hold,document,window),window.addEventListener("pointerup",this._windowPointerEnd),window.addEventListener("pointercancel",this._windowPointerEnd),window.addEventListener("keyup",this._windowKeyUp),this._focusLossCleanup=nt(window,document,()=>document.visibilityState==="hidden",()=>this._hold.releaseOnFocusLoss())}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===O)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config&&(this._compactStopTargets.size>0?this._stopCompact():this._hold.abandon()),(e.device_id!==this._config?.device_id||e.default_target!==this._config?.default_target)&&(this._activePairedPane=e.default_target??"both"),this._config=e}getCardSize(){if(this._config?.layout!=="compact")return 8;let e=this._config;return Math.ceil((24+(e.show_header!==!1?36:0)+(e.show_graphic!==!1?150:0)+(e.compact_labels!=="none"?40:0)+(e.compact_actions?.length===0?0:110)+(e.show_motors===!0?180:0)+(e.show_lighting===!0?70:0)+(e.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){window.removeEventListener("pointerup",this._windowPointerEnd),window.removeEventListener("pointercancel",this._windowPointerEnd),window.removeEventListener("keyup",this._windowKeyUp),this._focusLossCleanup?.(),this._focusLossCleanup=null,this._removeHoldLifecycle?.(),this._removeHoldLifecycle=void 0,super.disconnectedCallback(),this._hold.abandon()}shouldUpdate(e){if(e.has("_config")||e.has("_saveModeFor")||e.has("_activePairedPane")||e.has("_synchronizingTo")||e.has("_synchronizationFailed")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return p;if(!this._config.device_id)return this._notice("card.no_device");let e=_e(this.hass,this._config.device_id),t=te(this.hass,e);if(e&&t.length)return this._renderPaired(e,t);if(this._config.device_id&&me(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=E(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),P(i)?this._notice("card.no_entities"):this._config.layout==="compact"?this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:i}],!1):u`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(e,t="theme",i,o,r){let l=this._config,d={graphic:()=>l.show_graphic!==!1?i??this._graphic(e,t):p,motors:()=>l.show_motors!==!1?this._motors(e,o,r):p,firmness:()=>l.show_firmness!==!1?this._firmness(e):p,presets:()=>l.show_presets!==!1?this._presets(e):p,memory:()=>l.show_memory!==!1?this._memory(e):p,lighting:()=>l.show_lighting!==!1?this._lighting(e):p,massage:()=>l.show_massage!==!1?this._massage(e):p,utility:()=>l.show_utility!==!1?this._utility(e):p,climate:()=>l.show_climate!==!1?this._climate(e):p,connection:()=>l.show_connection!==!1?this._connection(e):p};return this._orderedSections().map(h=>d[h]?.()??p)}_renderPaired(e,t){let i=this.hass,o=E(i,e),r=t.map((g,y)=>({key:g,label:this._deviceLabel(g),bed:E(i,g),graphicTone:y===0?"left":"right",synchronizationTarget:{deviceId:g}})),l=r.flatMap(g=>g.bed.stop?[g.bed.stop]:[]),d=o.stop,h=[...new Set([...d?[d]:[],...l])],f=[{key:"both",label:m(i,"card.both_sides"),bed:o,stopScope:h,remainingStopIds:l},...r.map(g=>({...g,stopScope:g.bed.stop?[g.bed.stop]:[]}))];return this._watched=[o,...r.map(g=>g.bed)].flatMap(g=>this._collectWatched(g)),P(o)&&r.every(g=>P(g.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,f)}_renderSingleAddressPaired(e){let t=this.hass,i={both:E(t,e,"both"),left:E(t,e,"left"),right:E(t,e,"right")},o=[i.left.stop,i.right.stop].filter(r=>r!==void 0);return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>P(r))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:m(t,"card.both_sides"),bed:i.both,stopScope:[...new Set([i.both.stop,...o].filter(r=>r!==void 0))],remainingStopIds:o},{key:"left",label:m(t,"card.left_side"),bed:i.left,graphicTone:"left",stopScope:i.left.stop?[i.left.stop]:[],synchronizationTarget:{deviceId:e,side:"left"}},{key:"right",label:m(t,"card.right_side"),bed:i.right,graphicTone:"right",stopScope:i.right.stop?[i.right.stop]:[],synchronizationTarget:{deviceId:e,side:"right"}}])}_renderPairedCard(e,t){if(this._config?.layout==="compact")return this._renderCompact(e,t,!0);let i=t.filter(d=>!P(d.bed)),o=i.find(d=>d.key===this._activePairedPane)??i[0],r=i.filter(d=>d.key!=="both"),l=o.key==="both";return u`
      <ha-card class="paired-card">
        ${this._header(o.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(d=>u`
              <button
                class="pane-tab side-${d.graphicTone??"theme"} ${d.key===o.key?"active":""}"
                role="tab"
                aria-selected=${d.key===o.key?"true":"false"}
                @click=${()=>this._selectPairedPane(d.key)}
              >
                ${d.graphicTone?u`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span>${d.key==="both"?m(this.hass,"card.both"):d.label}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${o.label}>
          ${this._renderSections(o.bed,o.graphicTone,l?this._pairedOverview(r):void 0,o.stopScope,o.remainingStopIds)}
          ${l&&this._config?.show_lighting!==!1?this._combinedLighting(o.bed,r):p}
          ${l&&this._config?.show_connection!==!1?this._combinedBluetooth(r):p}
        </div>
      </ha-card>
    `}_renderCompact(e,t,i){let o=this._config,r=t.find(b=>b.key===this._activePairedPane),l=r?.bed,d=l?Se(this.hass,l,o.compact_actions):[],h=o.show_motors===!0&&l?l.motors.filter(b=>b.cover||b.up||b.down||b.position):[],f=d.length>0||h.length>0||o.show_lighting===!0,g=o.compact_actions?.length!==0||o.show_motors===!0||o.show_lighting===!0,y=i?t.filter(b=>b.key!=="both"):t,x=!!l&&Ee(l).length>0,v=d.length>0||h.length>0,$=Te(o.navigation_path);return u`
      <ha-card class="compact-card ${g?"":"compact-glance"} ${o.animate===!1?"no-animation":""}">
        ${o.show_header!==!1?u`
          <div class="compact-header">
            <span class="title">${this._title(e)}</span>
            ${$?u`<button class="compact-open" @click=${this._navigate}
              aria-label=${m(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:p}
          </div>`:p}
        ${i&&g?o.show_side_selector!==!1?u`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${t.filter(b=>!P(b.bed)).length}`}
            aria-label=${m(this.hass,"compact.target")}>
            ${t.filter(b=>!P(b.bed)).map(b=>u`
              <button class="pane-tab side-${b.graphicTone??"theme"} ${b.key===r?.key?"active":""}"
                aria-pressed=${b.key===r?.key?"true":"false"}
                title=${b.label}
                @click=${()=>this._selectPairedPane(b.key)}>
                ${b.graphicTone?u`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span class="compact-tab-label">${b.key==="both"?m(this.hass,"card.both"):b.label}</span>
              </button>`)}
          </div>`:u`<div class="compact-target">
            ${m(this.hass,"compact.target")}: ${r?.label??m(this.hass,"compact.target_missing")}
          </div>`:p}
        ${o.show_graphic!==!1?this._compactGraphic(y):p}
        ${this._compactReadouts(y)}
        ${!r&&g?u`<div class="hint" role="status">
          ${m(this.hass,"compact.target_missing")}</div>`:p}
        ${h.length?u`<div class="rows compact-motors">
          ${h.map(b=>b.cover||b.up||b.down?this._motorRow(b,l?.stop,!0,r?.stopScope,r?.remainingStopIds):this._moreInfoRow(b.position))}
        </div>`:p}
        ${d.length||v||this._compactStopTargets.size?u`
          <div class="tiles compact-actions">
            ${d.map(({entityId:b})=>u`<button class="tile"
              ?disabled=${!x||!this._available(b)}
              @click=${()=>this._compactRecall(b,l)}>
              ${this._icon(b)}<span class="tile-label">${this._name(b)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!x&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(l)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${m(this.hass,"action.stop")}</span>
            </button>
          </div>`:p}
        ${o.show_lighting===!0&&l?u`
          ${this._lighting(l)}
          ${i&&r?.key==="both"?this._combinedLighting(l,y):p}
        `:p}
        ${o.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(y):u`<div class="compact-connections">
          ${y.map(b=>{let _=this._connectionStatus(b.bed);return _?u`<span>${this._connectionDot(b.bed)}
              ${b.label}: ${m(this.hass,`status.${_}`)}</span>`:p})}
        </div>`:p}
        ${!f&&o.show_graphic===!1&&o.compact_labels==="none"&&o.show_header===!1&&o.show_connection!==!0?u`<div class="hint">${this._title(e)}</div>`:p}
      </ha-card>`}_compactGraphic(e){let t=e.map(h=>this._graphicState(h.bed)),i=t[0],o=t[1],r=t.length>0&&t.every(h=>h!==void 0),l=e.map((h,f)=>`${h.label}: ${t[f]?this._positionSummary(t[f]):m(this.hass,"compact.no_position")}`).join(". "),d=r&&i?o?Ye({left:i,right:o}):Ve({...i,upper:{angle:i.upper.angle},lower:{angle:i.lower.angle}}):u`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${m(this.hass,"compact.no_position")}</span></div>`;return Te(this._config?.navigation_path)?u`<button class="compact-graphic" @click=${this._navigate}
          aria-label="${m(this.hass,"compact.open")}. ${l}">${d}</button>`:u`<div class="compact-graphic" role="img" aria-label=${l}>${d}</div>`}_compactReadouts(e){let t=this._config?.compact_labels??"angles";return t==="none"?p:u`<div class="compact-readouts ${t==="names"?"compact-names":""}">
      ${e.map(i=>u`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span aria-label=${i.label}>${t==="angles"&&e.length>1?[...i.label][0]:i.label}</span>
        </span>
        ${t==="angles"?u`<span class="compact-position"
          title=${i.bed.motors.map(o=>`${this._motorName(o)} ${this._readout(o)??"?"}`).join(" \xB7 ")}
        >${i.bed.motors.filter(o=>o.angle||o.position||o.cover).map(o=>this._readout(o)??"?").join(" / ")||m(this.hass,"compact.no_position")}</span>`:p}
      </div>`)}
    </div>`}_available(e){let t=this._state(e)?.state;return t!==void 0&&t!=="unavailable"}_compactRecall(e,t){this._hold.abandon(),Ee(t).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(e),this.requestUpdate()}_stopCompact(e){let t=[...new Set([...e?Ee(e):[],...this._compactStopTargets.keys()])];this._hold.cancelForStopScope(t);for(let i of t)this._compactStopTargets.has(i)||this._compactStopTargets.set(i,Symbol());for(let i of this._compactStopTargets.keys())this._stopCompactTarget(i);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(e,t=e){let i=this._compactStopTargets.get(t),o=e.startsWith("cover.");this.hass?.callService(o?"cover":"button",o?"stop_cover":"press",{entity_id:e}).then(()=>{i!==void 0&&this._compactStopTargets.get(t)===i&&(this._compactStopTargets.delete(t),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(e){this._activePairedPane!==e&&(this._activePairedPane=e,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.attributes?.state_detail==="connecting"?"connecting":t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?u`<span
      class="connection-dot ${t}"
      title=${m(this.hass,`status.${t}`)}
    ></span>`:p}_pairedOverview(e){let t=e.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(t.length<2)return p;let[i,o]=t;return u`
      <div class="graphic dual-graphic">
        ${Ye({left:i.graphic,right:o.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,o].map(({pane:r,graphic:l},d)=>u`
            <div class="dual-readout side-${d===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(l)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,o.pane)}
    `}_synchronizeSelector(e,t){if(!e.synchronizationTarget||!t.synchronizationTarget)return p;let i=this._synchronizationPlan(e.bed,t.bed),o=this._synchronizationPlan(t.bed,e.bed);if(i.length===0&&o.length===0)return p;let r=this._synchronizingTo!==void 0;return u`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${m(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${m(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"left")}
          >
            ${this._synchronizingTo==="left"?u`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:u`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${m(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||o.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"right")}
          >
            ${this._synchronizingTo==="right"?u`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:u`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?u`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${m(this.hass,"sync.incomplete")}</span>
          </div>`:p}
    `}_synchronizationPlan(e,t){let i=new Map(t.motors.map(l=>[l.key,l])),o=e.motors.filter(l=>hi.has(l.key)&&i.has(l.key)&&this._hasPositionFeedback(l)&&this._hasPositionFeedback(i.get(l.key)));if(o.length===0)return[];let r=o.map(l=>({motor:l.key,position:this._angle(l)}));return r.some(l=>l.position===void 0)||o.some(l=>this._angle(i.get(l.key))===void 0)?[]:r}_hasPositionFeedback(e){return e.angle!==void 0||e.position!==void 0}async _synchronizePositions(e,t,i){if(this._synchronizingTo||!this.hass)return;let o=i==="left"?e:t,r=i==="left"?t:e,l=r.synchronizationTarget;if(!l)return;let d=this._synchronizationPlan(o.bed,r.bed);if(d.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(O,"set_positions",{device_id:[l.deviceId],positions:d,...l.side?{side:l.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,e.lowerMotor]).map(i=>{let o=this._readout(i);return o?`${this._motorName(i)} ${o}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return p;let i=t.map(f=>this._mainLight(f.bed)).filter(f=>f!==void 0);if(i.length===0)return p;let o=i.filter(f=>this._state(f)?.state==="on").length,r=o===i.length,l=o>0,d=r?"combined.on":l?"combined.mixed":"combined.off",h=m(this.hass,"combined.lights");return u`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${l?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${h}</span>
          <span class="secondary">${m(this.hass,d)}</span>
        </div>
        <button
          class="toggle ${l?"on":""} ${l&&!r?"mixed":""}"
          role="switch"
          aria-label=${h}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(e){let t=e.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return t.length===0?p:u`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${t.map(({pane:i,entityId:o})=>{let r=this._connectionStatus(i.bed),d=this._state(o)?.attributes.rssi;return u`
            <div class="bluetooth-receiver" role="group" aria-label=${i.label}>
            <button
              class="bluetooth-status ${r}"
              @click=${()=>this._moreInfo(o)}
            >
              <ha-icon
                icon=${r==="connected"?"mdi:bluetooth-connect":r==="connecting"?"mdi:bluetooth-transfer":r==="idle"?"mdi:bluetooth":"mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${i.label}</span>
                <span class="bluetooth-detail">
                  ${m(this.hass,`status.${r}`)}${typeof d=="number"?` \xB7 ${d} dBm`:""}
                </span>
              </span>
            </button>
            <div class="tiles">
              ${i.bed.connect?this._tile(i.bed.connect,()=>this._press(i.bed.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):p}
              ${i.bed.disconnect?this._tile(i.bed.disconnect,()=>this._press(i.bed.disconnect),{icon:"mdi:bluetooth-off"}):p}
            </div>
            </div>
          `})}
      </div>
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){return I(e.lights)}_deviceLabel(e){let t=this.hass?.devices[e];return t?.name_by_user??t?.name??e}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...U];let t=new Set(U),i=e.filter(r=>t.has(r)),o=U.filter(r=>!i.includes(r));return[...i,...o]}_header(e,t){let i=this._connectionStatus(e),o={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return u`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?p:u`
                <button
                  class="conn ${o[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${m(this.hass,o[i].key)}
                >
                  <ha-icon icon=${o[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?u`
      <div class="graphic">
        ${Ve(i,t)}
      </div>
    `:p}_graphicState(e){let t=e.motors.filter(d=>{let h=d.angle??d.position;return h!==void 0&&this._state(h)?.attributes.unit_of_measurement==="\xB0"});if(t.length===0||t.some(d=>this._angle(d)===void 0))return;let i=Je(t);if(!i)return;let{upper:o,lower:r}=i,l=e.motors.some(d=>{let h=d.cover?this._state(d.cover)?.state:void 0;return h==="opening"||h==="closing"});return{upperMotor:o,lowerMotor:r,upper:{label:this._motorName(o),angle:this._angle(o)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:l}}_motors(e,t,i){let o=t??(e.stop?[e.stop]:[]),r=e.motors.filter(h=>h.cover||h.up||h.down),l=e.motors.filter(h=>h.position&&!h.cover&&!h.up&&!h.down);if(r.length===0&&l.length===0&&!e.synchro&&!e.controlSide&&!e.stop)return p;let d=r.length>0||l.length>0||!!e.synchro||!!e.controlSide;return u`
      ${d?this._heading("section.position"):p}
      ${e.controlSide?this._moreInfoRow(e.controlSide):p}
      ${e.synchro?this._toggleRow(e.synchro):p}
      ${r.length?u`<div class="rows">
              ${r.map(h=>this._motorRow(h,e.stop,!1,o,i))}
            </div>`:p}
      ${l.length?u`<div class="rows">
              ${l.map(h=>this._moreInfoRow(h.position))}
            </div>`:p}
      ${e.stop?u`<button class="stop-all" @click=${()=>ge(this._hold,e.stop,o,void 0,this.hass)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${m(this.hass,"action.stop_all")}</span>
            </button>`:p}
    `}_firmness(e){return e.firmness.length===0?p:u`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t,i=!1,o,r){let l=this._readout(e),d=!!e.cover||!!t,h=u`
      <span>${this._motorName(e)}</span>
      ${l&&!i?u`<span class="readout">${l}</span>`:p}
    `;return u`
      <div class="row">
        ${e.position?u`<button
              class="row-label position-label"
              aria-label=${this._name(e.position)}
              @click=${()=>this._moreInfo(e.position)}
            >${h}</button>`:u`<div class="row-label">${h}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(e,"down",t,o,r):p}
          ${this._motorDirection(e,"up",t,o,r)}
          ${i?p:u`<button
            class="cg-btn"
            aria-label=${m(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e,t,o)}
            ?disabled=${!d}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?p:this._motorDirection(e,"down",t,o,r)}
        </div>
      </div>
    `}_motorDirection(e,t,i,o,r){let l=e.cover??e[t],d=!!e.cover||!!i;return u`
      <button class="cg-btn"
        aria-label=${m(this.hass,`action.${t}`)}
        @pointerdown=${h=>this._startHold(h,e,t,i,o,r)}
        @pointerup=${h=>this._endPointerHold(h,e,i)}
        @pointercancel=${h=>this._endPointerHold(h,e,i)}
        @keydown=${h=>this._startHold(h,e,t,i,o,r)}
        @keyup=${h=>this._endKeyHold(h,e,i)}
        @blur=${()=>this._hold.endKeyboard(e,i)}
        @click=${h=>this._activateWithoutPointer(h,e,t,i,o)}
        ?disabled=${!l||this._config?.layout==="compact"&&(!d||!this._available(l))}
      ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}_presets(e){return e.presets.length===0?p:u`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._actionTile(t,e.stop))}
      </div>
    `}_utility(e){return e.utility.length===0&&!e.utilityNumbers?.length&&!e.utilitySelects?.length&&!e.utilityStates?.length?p:u`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._actionTile(t,e.stop,()=>t.startsWith("switch.")?this._call("switch","toggle",t):this._press(t)))}
      </div>
      ${e.utilitySelects?.map(t=>this._moreInfoRow(t))}
      ${e.utilityNumbers?.map(t=>this._moreInfoRow(t))}
      ${e.utilityStates?.map(t=>this._moreInfoRow(t))}
    `}_actionTile(e,t,i=()=>this._press(e)){let o=it(this.hass,e);return o?this._heldActionTile(e,o,t):this._tile(e,i)}_heldActionTile(e,t,i){return u`<button class="tile"
      aria-label=${this._name(e)}
      @pointerdown=${o=>this._startHold(o,t,"up",i)}
      @pointerup=${o=>this._endPointerHold(o,t,i)}
      @pointercancel=${o=>this._endPointerHold(o,t,i)}
      @keydown=${o=>this._startHold(o,t,"up",i)}
      @keyup=${o=>this._endKeyHold(o,t,i)}
      @blur=${()=>this._endHold(t,i)}
      @click=${o=>this._activateWithoutPointer(o,t,"up",i)}
      ?disabled=${!i||!this._available(e)}>
      ${this._icon(e)}
      <span class="tile-label">${this._name(e)}</span>
    </button>`}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let d=new Set(i.map(Number));t=t.filter(h=>d.has(h.slot))}if(t.length===0)return p;let o=this._config?.memory_save!==!1&&t.some(d=>d.save),r=t.map(d=>d.save??d.goto??String(d.slot)).join("|"),l=this._saveModeFor===r;return u`
      <div class="section-heading heading-row">
        <span>${m(this.hass,"section.memory")}</span>
        ${o?u`<button
                class="set-btn ${l?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${l?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${m(this.hass,l?"memory.cancel":"memory.set")}</span>
              </button>`:p}
      </div>
      ${l?u`<div class="hint">${m(this.hass,"memory.set_hint")}</div>`:p}
      <div class="tiles">${t.map(d=>this._memoryTile(d,l,e.stop))}</div>
    `}_memoryTile(e,t,i){let o=e.goto??e.save;if(t){let l=!!e.save;return u`
        <button
          class="tile ${l?"save-mode":"is-disabled"}"
          ?disabled=${!l}
          @click=${()=>l&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(o)}</span>
        </button>
      `}let r=!!e.goto;return r?this._actionTile(e.goto,i):u`
      <button
        class="tile ${r?"":"is-disabled"}"
        ?disabled=${!r}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(o)}
        <span class="tile-label">${this._name(o)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;if(!I(t)&&!t.state)return p;let o=i||t.state||t.level||t.numbers?.length||t.timer||t.toggle||t.cycle||t.timerMinutes||t.timerToggle||t.buttons?.length;return u`
      ${this._heading("section.lighting")}
      ${t.mood&&o?this._subheading("lighting.floor"):p}
      ${i?this._toggleRow(i):p}
      ${t.state?this._moreInfoRow(t.state):p}
      ${t.states?.map(r=>this._moreInfoRow(r))}
      ${t.level?this._moreInfoRow(t.level):p}
      ${t.numbers?.map(r=>this._moreInfoRow(r))}
      ${t.timer?this._moreInfoRow(t.timer):p}
      ${t.timerMinutes?this._moreInfoRow(t.timerMinutes):p}
      ${!t.timerAppliesImmediately&&(t.timerMinutes||t.timerToggle)?u`<div class="hint">${m(this.hass,"lighting.timer_pending")}</div>`:p}
      ${t.toggle||t.cycle||t.timerToggle||t.buttons?.length?u`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):p}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):p}
              ${t.timerToggle?this._tile(t.timerToggle,()=>this._press(t.timerToggle)):p}
              ${t.buttons?.map(r=>this._actionTile(r,e.stop))}
            </div>`:p}
      ${t.mood?u`
        ${this._subheading("lighting.mood")}
        ${t.mood.selects.map(r=>this._moreInfoRow(r))}
        ${t.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${t.mood.toggle||t.mood.buttons?.length?u`<div class="tiles">
          ${t.mood.toggle?this._tile(t.mood.toggle,()=>this._press(t.mood.toggle)):p}
          ${t.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:p}
      `:p}
    `}_massage(e){let t=e.massage;return t.buttons.length===0&&t.numbers.length===0&&!t.selects?.length&&!t.states?.length&&!t.timer?p:u`
      ${this._heading("section.massage")}
      ${t.buttons.length?u`<div class="tiles">
              ${t.buttons.map(i=>this._actionTile(i,e.stop))}
            </div>`:p}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.selects?.map(i=>this._moreInfoRow(i))}
      ${t.states?.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):p}
    `}_climate(e){let t=[...e.climate.entities,...e.climate.selects,...e.climate.numbers];return t.length===0?p:u`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?p:u`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):p}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):p}
      </div>
    `}_heading(e){return u`<div class="section-heading">${m(this.hass,e)}</div>`}_subheading(e){return u`<div class="lighting-heading">${m(this.hass,e)}</div>`}_tile(e,t,i={}){return u`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${this._name(e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",o=this._name(e);return u`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${o}
        @click=${()=>this._moreInfo(e)}
        @keydown=${r=>this._onRowKey(r,()=>this._moreInfo(e))}
      >
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${o}</span>
          <span class="secondary">${this._stateText(e)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${o}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(e)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(e){let t=this._name(e);return u`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${t}
        @click=${()=>this._moreInfo(e)}
        @keydown=${i=>this._onRowKey(i,()=>this._moreInfo(e))}
      >
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${t}</span>
        </div>
        <span class="secondary value">${this._stateText(e)}</span>
      </div>
    `}_icon(e,t){let i=this._state(e);return i?u`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:u`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return u`<ha-card><div class="notice">${m(this.hass,e)}</div></ha-card>`}_state(e){return this.hass?.states[e]}_title(e){return this._config?.name?this._config.name:this._deviceName(e)??m(this.hass,"card.default_name")}_deviceName(e=this._config?.device_id){let t=e?this.hass?.devices[e]:void 0;return t?.name_by_user||t?.name||void 0}_name(e){let t=this._state(e)?.attributes.friendly_name??this.hass?.entities[e]?.name??e,i=this.hass?.entities[e]?.device_id,o=this._deviceName(i);return o&&t.startsWith(o+" ")?t.slice(o.length+1):t}_motorName(e){let t=`motor.${e.key}`,i=m(this.hass,t);return i!==t?i:e.key.split("_").map(o=>o.charAt(0).toUpperCase()+o.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){let t=e.angle??e.position;if(t){let i=this._angle(e);if(i===void 0)return;let o=this._state(t)?.attributes.unit_of_measurement,r=e.angle?"\xB0":"%";return`${Math.round(i)}${typeof o=="string"?o:r}`}if(e.cover){let i=this._state(e.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(o=>o&&t.add(o));e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(o=>o&&t.add(o));return[e.stop,e.synchro,e.controlSide,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.state,...e.lights.states??[],e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.lights.timerMinutes,e.lights.timerToggle,e.lights.mood?.toggle,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.lights.buttons?.forEach(i=>t.add(i)),e.lights.numbers?.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.massage.selects?.forEach(i=>t.add(i)),e.massage.states?.forEach(i=>t.add(i)),e.lights.mood?.selects.forEach(i=>t.add(i)),e.lights.mood?.numbers.forEach(i=>t.add(i)),e.lights.mood?.buttons?.forEach(i=>t.add(i)),e.utility.forEach(i=>t.add(i)),e.utilityNumbers?.forEach(i=>t.add(i)),e.utilitySelects?.forEach(i=>t.add(i)),e.utilityStates?.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),e.climate.numbers.forEach(i=>t.add(i)),[...t]}_startHold(e,t,i,o,r,l){let d=null;if(e instanceof KeyboardEvent){if(e.key!=="Enter"&&e.key!==" "||(e.preventDefault(),e.repeat))return}else{if(e.button!==0||!e.isPrimary)return;e.currentTarget.setPointerCapture?.(e.pointerId),e.preventDefault(),d=e.pointerId}this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):t.cover&&this._compactStopTargets.set(t.cover,Symbol()),this.requestUpdate()),this._hold.start(t,i,d,o,r??(o?[o]:[]),l,e instanceof KeyboardEvent?e.key:null,X(this.hass,o??t.holdEntityId??t.cover??t[i]))}_activateWithoutPointer(e,t,i,o,r){e.detail!==0||this._hold.heldKey!==null||(this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):t.cover&&this._compactStopTargets.set(t.cover,Symbol()),this.requestUpdate()),this._hold.claimStopScope([...r??[],...o?[o]:[],...t.cover?[t.cover]:[]],X(this.hass,o??t.holdEntityId??t.cover??t[i])),ot(this.hass,t,i))}_endPointerHold(e,t,i){this._hold.endFromPointer(t,e.pointerId,e.type!=="pointerup"||e.button===0,i)}_endKeyHold(e,t,i){e.key!=="Enter"&&e.key!==" "||(e.stopPropagation(),this._hold.endKeyboard(t,i,e.key))}_endHold(e,t){this._hold.end(e,t)}_motorStop(e,t,i){if(e.cover){i?.length?ge(this._hold,e.cover,[...i,e.cover],e.coverStopScope==="side"?void 0:e.key,this.hass):(this._hold.stopCover(e,X(this.hass,e.cover),e.coverStopScope??"motor",t,Pe(this.hass,e.cover)),this._cover(e.cover,"stop_cover"));return}ge(this._hold,t,i,void 0,this.hass)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};M.styles=se`
    .compact-card { padding: 13px; }
    .compact-header { display: grid; grid-template-columns: minmax(0, 1fr) 24px;
      align-items: center; gap: 8px; min-height: 22px; padding: 0 2px 9px; }
    .compact-header .title { font-size: 14px; line-height: 22px; font-weight: 700; }
    .compact-open { display: grid; place-items: center; padding: 0; border: 0;
      background: none; color: var(--secondary-text-color); cursor: pointer;
      width: 24px; height: 22px; }
    .compact-open ha-icon { --mdc-icon-size: 16px; }
    .compact-card .compact-tabs { margin: 0; }
    .compact-tabs .pane-tab {
      min-height: 38px; height: auto; padding: 4px 5px; gap: 4px;
      font-size: 11px;
    }
    .compact-tabs .dual-swatch, .compact-readouts .dual-swatch { width: 6px; height: 6px; }
    .compact-tabs .compact-tab-label { min-width: 0; }
    .compact-target { color: var(--secondary-text-color); font-size: .8rem; padding: 6px 0; }
    .compact-graphic { display: block; box-sizing: border-box; width: 100%; padding: 0;
      border: 0; border-radius: 8px; background: none; color: var(--primary-text-color); }
    button.compact-graphic { cursor: pointer; }
    .compact-graphic .bed-graphic { display: block; width: 100%; height: 132px; max-width: 300px; margin: auto; }
    .compact-glance .compact-graphic .bed-graphic { height: 112px; }
    .compact-no-position { min-height: 90px; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 8px; font-size: .75rem;
      color: var(--secondary-text-color); }
    .compact-no-position ha-icon { --mdc-icon-size: 36px; }
    .compact-readouts { display: flex; justify-content: space-between; gap: 8px;
      padding: 0 2px 12px; font-size: 11px; line-height: 17px; color: var(--secondary-text-color); }
    .compact-readouts > div { min-width: 0; display: flex; align-items: center; gap: 5px; }
    .compact-side-name { display: inline-flex; align-items: center; gap: 5px; }
    .compact-names { justify-content: center; flex-wrap: wrap; gap: 19px; padding: 4px 0 3px; }
    .compact-position { font-weight: 500; overflow-wrap: anywhere; }
    .side-theme .dual-swatch { background: var(--primary-color); }
    .compact-card .compact-actions { grid-template-columns: repeat(auto-fit, minmax(64px, 1fr)); gap: 7px; }
    .compact-actions .tile { min-height: 54px; padding: 5px 4px; gap: 2px;
      justify-content: center; }
    .compact-actions .tile .icon, .compact-actions .tile ha-icon { --mdc-icon-size: 22px; }
    .compact-actions .tile-label { font-size: 11px; line-height: 17px;
      white-space: normal; overflow-wrap: anywhere; }
    .compact-stop ha-icon { color: var(--error-color); }
    .compact-actions .tile:disabled { opacity: .45; cursor: default; }
    .compact-card .compact-motors { gap: 6px; margin: 0 0 10px; }
    .compact-motors .row { padding: 0; border: 0; border-radius: 0; gap: 6px; }
    .compact-motors .row-label { font-size: 12px; }
    .compact-connections { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px;
      font-size: .72rem; color: var(--secondary-text-color); }
    .compact-connections > span { display: inline-flex; align-items: center; gap: 5px; }
    .no-animation .bed-panel, .no-animation .dual-bed-panel { transition: none; }
    button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    @container bed-card (max-width: 258px) {
      .compact-card { padding: 10px; }
      .compact-header { min-height: 19px; }
      .compact-header .title { font-size: 12px; line-height: 19px; }
      .compact-open { height: 19px; }
      .compact-graphic .bed-graphic { height: 96px; }
      .compact-readouts { font-size: 9px; line-height: 14px; gap: 3px; padding-bottom: 10px; }
      .compact-tabs .pane-tab { min-height: 34px; font-size: 10px; }
      .compact-actions .tile { min-height: 44px; padding: 2px 3px; }
      .compact-actions .tile-label { font-size: 10px; line-height: 15px; }
      .compact-actions .tile .icon, .compact-actions .tile ha-icon { --mdc-icon-size: 20px; }
    }
    @media (prefers-reduced-motion: reduce) {
      :host .bed-panel, :host .dual-bed-panel { transition: none; }
    }

    :host {
      display: block;
      container: bed-card / inline-size;
      --ab-gap: 10px;
      --ab-control-surface: color-mix(in srgb, var(--card-background-color) 94%, var(--primary-text-color));
      --ab-control-border: color-mix(in srgb, var(--card-background-color) 85%, var(--primary-text-color));
      --ab-side-left-rgb: 115, 182, 237;
      --ab-side-right-rgb: 237, 144, 158;
    }
    ha-card {
      padding: 12px 12px 16px;
      overflow: hidden;
    }
    .header {
      /* Reserve the optional Bluetooth action across paired tab changes. */
      display: grid;
      grid-template-columns: 22px minmax(0, 1fr) 32px;
      min-height: 32px;
      align-items: center;
      gap: 10px;
      padding: 4px 4px 8px;
    }
    .header-icon {
      color: var(--state-icon-color, var(--primary-text-color));
      --mdc-icon-size: 22px;
    }
    .title {
      font-size: 1rem;
      font-weight: 700;
      color: var(--primary-text-color);
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .conn {
      box-sizing: border-box;
      width: 32px;
      height: 32px;
      align-items: center;
      justify-content: center;
      border: none;
      background: none;
      cursor: pointer;
      padding: 4px;
      border-radius: 50%;
      display: inline-flex;
      --mdc-icon-size: 20px;
    }
    .conn.ok {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .conn.connecting {
      color: var(--warning-color, var(--state-active-color, #ff9800));
    }
    .conn.idle {
      color: var(--info-color, var(--secondary-text-color));
    }
    .conn.off {
      color: var(--secondary-text-color);
    }
    .section-heading {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
      padding: 14px 4px 8px;
    }
    .lighting-heading {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      padding: 12px 4px 4px;
    }
    .pane-tabs {
      display: grid;
      grid-template-columns: repeat(var(--pane-count, 3), minmax(0, 1fr));
      gap: 3px;
      padding: 3px;
      margin: 0 0 6px;
      border-radius: 9px;
      background: color-mix(in srgb, var(--card-background-color) 45%,
        var(--primary-background-color, var(--card-background-color)));
    }
    .pane-tab {
      min-width: 0;
      min-height: 44px;
      padding: 4px 8px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--primary-text-color);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      font: inherit;
      font-size: .8rem;
      font-weight: 400;
      transition: background .15s ease;
      user-select: none;
      touch-action: manipulation;
    }
    .pane-tab .dual-swatch { width: 6px; height: 6px; }
    .pane-tab span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pane-tab:hover { background: var(--ab-control-surface); }
    .pane-tab.active {
      background: color-mix(in srgb, var(--secondary-background-color), var(--primary-color) 12%);
    }
    .connection-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--disabled-text-color);
      flex: none;
    }
    .connection-dot.connected {
      background: var(--success-color, var(--state-active-color, #43a047));
    }
    .connection-dot.connecting {
      background: var(--warning-color, var(--state-active-color, #ff9800));
    }
    .connection-dot.idle {
      background: var(--info-color, var(--secondary-text-color));
    }
    .connection-dot.disconnected {
      background: var(--error-color);
    }
    .pane {
      animation: ab-pane-in 0.16s ease-out;
    }
    @keyframes ab-pane-in {
      from {
        opacity: 0;
        transform: translateY(2px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    .heading-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .set-btn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1px solid var(--ab-control-border);
      background: var(--ab-control-surface);
      color: var(--primary-color);
      border-radius: 999px;
      padding: 4px 12px 4px 9px;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: none;
      cursor: pointer;
      --mdc-icon-size: 16px;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .set-btn:hover {
      background: var(--secondary-background-color);
    }
    .set-btn.active {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .hint {
      font-size: 0.8rem;
      color: var(--secondary-text-color);
      padding: 0 6px 8px;
    }
    .tile.save-mode {
      border-color: var(--primary-color);
      border-style: dashed;
    }
    .tile.save-mode .icon {
      color: var(--primary-color);
    }
    .tile.is-disabled {
      opacity: 0.4;
      cursor: default;
    }
    .graphic {
      display: flex;
      justify-content: center;
      padding: 4px 8px 0;
    }
    .bed-graphic {
      width: 100%;
      max-width: 350px;
      height: auto;
      overflow: visible;
    }
    .bed-graphic-theme {
      --ab-graphic-rgb: var(--rgb-primary-color, 33, 150, 243);
    }
    .bed-graphic-left {
      --ab-graphic-rgb: var(--ab-side-left-rgb);
    }
    .bed-graphic-right {
      --ab-graphic-rgb: var(--ab-side-right-rgb);
    }
    .bed-graphic.is-moving {
      opacity: 0.95;
    }
    .bed-frame-stop {
      stop-color: var(--secondary-text-color);
    }
    .bed-graphic-theme .bed-mattress-stop {
      stop-color: rgb(var(--rgb-primary-color, 33, 150, 243));
    }
    .bed-graphic-left .bed-mattress-stop,
    .dual-bed-left-stop {
      stop-color: rgb(var(--ab-side-left-rgb));
    }
    .bed-graphic-right .bed-mattress-stop,
    .dual-bed-right-stop {
      stop-color: rgb(var(--ab-side-right-rgb));
    }
    .bed-frame,
    .dual-bed-frame {
      fill: var(--secondary-text-color);
      opacity: .55;
      stroke: none;
    }
    .bed-side-layer {
      opacity: 0.86;
    }
    .bed-graphic-left .bed-side-layer,
    .bed-graphic-right .bed-side-layer {
      opacity: 0.66;
    }
    .bed-surface,
    .dual-bed-surface {
      stroke: var(--primary-text-color);
      stroke-opacity: .65;
      stroke-width: .7px;
      vector-effect: non-scaling-stroke;
    }
    .dual-bed-left-stop, .dual-bed-right-stop { stop-opacity: 1; }
    .bed-pillow,
    .dual-bed-pillow {
      opacity: 0.9;
    }
    .bed-panel {
      transition: transform 0.55s cubic-bezier(0.2, 0.7, 0.2, 1);
    }
    .bed-graphic-label {
      fill: var(--secondary-text-color);
      font-size: 11px;
      font-family: var(--ha-font-family-body, var(--primary-font-family, sans-serif));
    }
    .dual-graphic {
      padding-top: 8px;
    }
    .dual-bed-graphic {
      isolation: isolate;
    }
    .dual-bed-side {
      opacity: 0.66;
    }
    .dual-bed-panel {
      transition: transform 0.55s cubic-bezier(0.2, 0.7, 0.2, 1);
    }
    .dual-bed-side.is-moving {
      stroke-width: 1.5;
    }
    .dual-readouts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      width: min(100%, 350px);
      margin: -2px auto 2px;
    }
    .dual-readout {
      min-width: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
      padding: 8px 10px;
      text-align: center;
    }
    .dual-side-name {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--primary-text-color);
      font-size: 0.8rem;
      font-weight: 600;
    }
    .dual-swatch {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex: none;
    }
    .side-left .dual-swatch {
      background: rgb(var(--ab-side-left-rgb));
    }
    .side-right .dual-swatch {
      background: rgb(var(--ab-side-right-rgb));
    }
    .dual-position {
      overflow: hidden;
      color: var(--secondary-text-color);
      font-size: 0.72rem;
      line-height: 1.25;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-row {
      box-sizing: border-box;
      width: min(100%, 350px);
      min-height: 52px;
      margin: 4px auto 2px;
      padding: 7px 9px;
      display: flex;
      align-items: center;
      gap: 8px;

      border-radius: 11px;

    }
    .dual-sync-row > ha-icon {
      flex: none;
      color: var(--secondary-text-color);
      --mdc-icon-size: 19px;
    }
    .dual-sync-label {
      min-width: 0;
      flex: 1;
      color: var(--primary-text-color);
      font-size: 0.78rem;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 4px;
      min-width: 148px;
      max-width: 52%;
      flex: none;
    }
    .dual-sync-btn {
      min-width: 0;
      height: 34px;
      padding: 0 9px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      background: var(--ab-control-surface);
      color: var(--primary-text-color);
      font: inherit;
      font-size: 0.74rem;
      font-weight: 500;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease, opacity 0.15s ease;
    }
    .dual-sync-btn:hover:not(:disabled),
    .dual-sync-btn:focus-visible {
      border-color: var(--primary-color);
    }
    .dual-sync-btn:disabled {
      cursor: default;
      opacity: 0.42;
    }
    .dual-sync-btn.is-active {
      opacity: 1;
      border-color: var(--primary-color);
      background: var(--secondary-background-color);
    }
    .dual-sync-btn span:last-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-spinner {
      flex: none;
      color: var(--primary-color);
      --mdc-icon-size: 15px;
    }
    .dual-sync-error {
      box-sizing: border-box;
      width: min(100%, 350px);
      margin: 5px auto 2px;
      padding: 6px 9px;
      display: flex;
      align-items: center;
      gap: 6px;
      border-radius: 9px;
      background: color-mix(in srgb, var(--error-color) 12%, transparent);
      color: var(--error-color);
      font-size: 0.72rem;
    }
    .dual-sync-error ha-icon {
      flex: none;
      --mdc-icon-size: 16px;
    }



    .rows {
      display: flex;
      flex-direction: column;
      gap: var(--ab-gap);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      padding: 6px 0;
    }
    .row-label {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-width: 90px;
    }
    .row-label .readout {
      color: var(--secondary-text-color);
      font-size: 0.82rem;
    }
    .position-label {
      border: 0;
      border-radius: 4px;
      padding: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      text-align: start;
      cursor: pointer;
    }
    .position-label .readout {
      color: var(--primary-color);
      text-decoration: underline dotted;
      text-underline-offset: 3px;
    }
    .control-group { display: inline-flex; gap: 6px; }
    .cg-btn {
      box-sizing: border-box;
      width: 44px;
      height: 44px;
      border: 1px solid var(--ab-control-border);
      border-radius: 8px;
      background: var(--ab-control-surface);
      color: var(--primary-color);
      cursor: pointer;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      --mdc-icon-size: 22px;
      transition: background 0.15s ease;
      /* Press-and-hold has to survive a slightly unsteady finger. Pointer
         capture and preventDefault() do not override the browser's touch
         gesture arbitration, so without this a small vertical drag starts
         scrolling the page, fires pointercancel and cuts the hold short. */
      touch-action: none;
    }
    .cg-btn:hover {
      background: var(--secondary-background-color);
    }
    .cg-btn:active {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.18);
    }
    .cg-btn[disabled] {
      color: var(--disabled-text-color);
      cursor: default;
    }
    .stop-all {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      margin-top: var(--ab-gap);
      padding: 10px;
      border-radius: 9px;
      cursor: pointer;
      background: var(--ab-control-surface);
      border: 1px solid var(--ab-control-border);
      color: var(--error-color);
      font-size: 0.9rem;
      font-weight: 500;
      --mdc-icon-size: 20px;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .stop-all:hover {
      background: var(--secondary-background-color);
    }
    .stop-all:active {
      border-color: var(--error-color);
    }
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
      gap: var(--ab-gap);
    }
    .tile {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      justify-content: center;
      min-height: 64px;
      padding: 8px 6px;
      background: var(--ab-control-surface);
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      cursor: pointer;
      color: var(--primary-text-color);
      transition: background 0.15s ease, border-color 0.15s ease;
      -webkit-user-select: none;
      user-select: none;
      touch-action: manipulation;
    }
    .tile:hover {
      background: var(--secondary-background-color);
    }
    .tile:active {
      border-color: var(--primary-color);
    }
    .tile .icon {
      color: var(--primary-color);
      --mdc-icon-size: 22px;
    }
    .tile.danger .icon {
      color: var(--error-color);
    }
    .tile.success .icon {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .tile-label {
      font-size: 0.78rem;
      text-align: center;
      line-height: 1.2;
    }
    .entity-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 12px;
      background: var(--ab-control-surface);
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      cursor: pointer;
      margin-bottom: var(--ab-gap);
    }
    .entity-row .icon {
      color: var(--state-icon-color, var(--primary-color));
      --mdc-icon-size: 24px;
    }
    .combined-entity-row {
      cursor: default;
    }
    .combined-entity-row .icon.active {
      color: var(--state-light-active-color, var(--state-active-color, #ffc107));
    }
    .entity-row-text {
      display: flex;
      flex-direction: column;
      flex: 1;
    }
    .entity-row-text .secondary,
    .value {
      color: var(--secondary-text-color);
      font-size: 0.82rem;
    }
    .toggle {
      width: 42px;
      height: 24px;
      border-radius: 12px;
      border: none;
      background: var(--switch-unchecked-track-color, rgba(120, 120, 120, 0.4));
      position: relative;
      cursor: pointer;
      padding: 0;
      transition: background 0.2s ease;
      flex: none;
    }
    .toggle.on {
      background: var(--primary-color);
    }
    .toggle.mixed {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.55);
    }
    .toggle .knob {
      position: absolute;
      top: 2px;
      left: 2px;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--switch-unchecked-button-color, #fff);
      transition: transform 0.2s ease;
    }
    .toggle.on .knob {
      transform: translateX(18px);
    }
    .bluetooth-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--ab-gap);
    }
    .bluetooth-receiver {
      min-width: 0;
      display: grid;
      gap: var(--ab-gap);
    }
    .bluetooth-status {
      min-width: 0;
      width: 100%;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--ab-control-border);
      border-radius: 9px;
      background: var(--ab-control-surface);
      color: var(--primary-text-color);
      cursor: pointer;
      font: inherit;
      text-align: left;
    }
    .bluetooth-status ha-icon {
      --mdc-icon-size: 22px;
      flex: none;
    }
    .bluetooth-status.connected ha-icon {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .bluetooth-status.connecting ha-icon {
      color: var(--warning-color, var(--state-active-color, #ff9800));
    }
    .bluetooth-status.idle ha-icon {
      color: var(--info-color, var(--secondary-text-color));
    }
    .bluetooth-status.disconnected ha-icon {
      color: var(--secondary-text-color);
    }
    .bluetooth-copy {
      min-width: 0;
      display: flex;
      flex-direction: column;
    }
    .bluetooth-detail {
      overflow: hidden;
      color: var(--secondary-text-color);
      font-size: 0.72rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .notice {
      padding: 24px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }
  `,C([Y({attribute:!1})],M.prototype,"hass",2),C([H()],M.prototype,"_config",2),C([H()],M.prototype,"_saveModeFor",2),C([H()],M.prototype,"_activePairedPane",2),C([H()],M.prototype,"_synchronizingTo",2),C([H()],M.prototype,"_synchronizationFailed",2);fe("adjustable-bed-card",M);console.info(`%c adjustable-bed-card %c ${Bt} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{M as AdjustableBedCard};
