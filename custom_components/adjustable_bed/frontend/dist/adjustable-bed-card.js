/* adjustable-bed-card 5.0.0b8 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var Si=Object.defineProperty;var Ti=Object.getOwnPropertyDescriptor;var C=(s,o,e,t)=>{for(var i=t>1?void 0:t?Ti(o,e):o,n=s.length-1,r;n>=0;n--)(r=s[n])&&(i=(t?r(o,e,i):r(i))||i);return t&&i&&Si(o,e,i),i};function Me(s,o,e=s?.entities[o]?.device_id){let t=s?.states[o]?.attributes,i=t?.hold_lease_mode;if(i!=="stream"&&i!=="latched"||!e)return;let n=t?.hold_lease_motor,r=t?.bed_side;return{deviceId:e,...typeof n=="string"&&n?{motor:n}:{},...r==="left"||r==="right"||r==="both"?{side:r}:{}}}function le(s,o){return s.holdLease?s.heldControls?.[o]??s.heldControl?!!s.deviceId:!!(s.timedMove??s.holdLease.motor):!1}function Ci(s,o){return!!(s.heldControls?.[o]??s.heldControl)||le(s,o)}var Mi=3e4;function St(s,o){return!(s.heldControls?.[o]??s.heldControl)||le(s,o)}function Tt(s,o,e,t){if(o.heldControls?.[e]??o.heldControl)return Ai(s,o,e,t);if(!le(o,e)||!o.holdLease)return;let i=o.timedMove??{deviceId:o.holdLease.deviceId,motor:o.holdLease.motor,side:o.holdLease.side};return s?.callService("adjustable_bed","timed_move",{device_id:i.deviceId,...i.side?{side:i.side}:{},motor:i.motor,direction:e,duration_ms:750,hold_owner:t.owner,hold_generation:t.generation})}function Ae(s,o){let e=s?.entities[o],i=s?.states[o]?.attributes?.hold_release_button_key;if(!(!e?.device_id||typeof i!="string"))return Object.values(s?.entities??{}).find(n=>n.device_id===e.device_id&&n.entity_id.startsWith("button.")&&n.translation_key===i)?.entity_id}function Ct(s,o){let e=s?.entities[o]?.device_id,t=s?.states[o]?.attributes;if(t?.requires_confirmation===!0)return;let i=t?.held_control,n=t?.hold_start_delay_ms,r=t?.hold_release_delay_ms;if(!e||typeof i!="string"||typeof n!="number"||!Number.isFinite(n)||n<0||typeof r!="number"||!Number.isFinite(r)||r<0)return;let a=Ae(s,o);if(typeof t?.hold_release_button_key=="string"&&!a)return;let l=Me(s,o,e);return{...a?{releaseButton:a}:{},...l?{holdLease:l}:{},key:o,up:o,deviceId:e,holdEntityId:o,heldControl:{control:i,startDelayMs:n,releaseDelayMs:r}}}function qe(s,o,e){if(o.timedMove)return s?.callService("adjustable_bed","timed_move",{device_id:o.timedMove.deviceId,...o.timedMove.side?{side:o.timedMove.side}:{},motor:o.timedMove.motor,direction:e,duration_ms:1e3});if(o.cover)return s?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:o.cover});let t=e==="up"?o.up:o.down;return t?s?.callService("button","press",{entity_id:t}):void 0}function Ai(s,o,e,t){let i=o.heldControls?.[e]??o.heldControl;if(!i||!o.deviceId)return;let n=s?.states[o.holdEntityId??o.cover??""]?.attributes.bed_side,r={device_id:[o.deviceId],control:i.control,duration:750/1e3,hold_owner:t.owner,hold_generation:t.generation};return(n==="left"||n==="right"||n==="both")&&(r.side=n),s?.callService("adjustable_bed","hold_control",r)}function Mt(s,o,e){qe(s,o,e)?.catch(()=>{})}function At(s,o,e,t){let i=()=>t(),n=()=>{e()&&t()};s.addEventListener("blur",i),o.addEventListener("visibilitychange",n);let r=!0;return()=>{r&&(r=!1,s.removeEventListener("blur",i),o.removeEventListener("visibilitychange",n))}}function Pt(s,o){let e=o[s]?.parent_device_id??o[s]?.via_device_id;return e&&o[e]?e:void 0}function Pi(s,o){return Object.values(o).some(e=>(e.parent_device_id??e.via_device_id)===s)}function Te(s,o){let e=s.states[o]?.attributes,t=e?.bed_side??e?.side,i=t==="left"||t==="right"||t==="both"?t:void 0,n=s.entities[o]?.translation_key==="stop_both"?"both":void 0;if(!(i&&n&&i!==n))return i??n}function Et(s,o){let e=s.entities[o];return e?.platform==="adjustable_bed"&&o.startsWith("button.")&&(e.translation_key==="stop"||e.translation_key==="stop_both")}function ee(s,o){if(!s||!o)return;let e=s.entities[o]?.device_id;if(!e)return;let t=s.devices??{},i=Pt(e,t),n=Te(s,o)??(!i&&Pi(e,t)?"both":void 0);return{deviceId:i&&n?i:e,side:n,physicalDeviceId:e,...i?{parentDeviceId:i}:{},...n==="both"?{physicalChildIds:Object.entries(t).filter(([,r])=>(r.parent_device_id??r.via_device_id)===e).map(([r])=>r)}:{}}}function Ri(s,o){return(s.parentDeviceId??s.deviceId)!==(o.parentDeviceId??o.deviceId)?!1:s.side==="both"||o.side==="both"?!0:s.side&&o.side?s.side===o.side:!s.physicalDeviceId||!o.physicalDeviceId||s.physicalDeviceId===o.physicalDeviceId}function Xe(s,o){if(!s||!o)return[];let e=s.entities[o]?.device_id;if(!e)return[];let t=Te(s,o);if(t==="left"||t==="right"){let p=t==="left"?"right":"left",u=Object.values(s.entities).filter(h=>h.entity_id!==o&&h.device_id===e&&Et(s,h.entity_id)&&Te(s,h.entity_id)===p);if(u.length===1)return[u[0].entity_id]}let i=s.devices??{},n=Pt(e,i);if(!n)return[];let r=Object.entries(i).filter(([,p])=>(p.parent_device_id??p.via_device_id)===n).map(([p])=>p);if(r.length!==2||!r.includes(e))return[];let a=r.find(p=>p!==e),l=Object.values(s.entities).filter(p=>{if(p.device_id!==a||!Et(s,p.entity_id))return!1;let u=Te(s,p.entity_id);return u!=="both"&&(u===void 0||u!==t)});return l.length===1?[l[0].entity_id]:[]}function Se(s){let o=s.holdEntityId??s.cover??s.up??s.down??"";return`${s.key}\0${o}`}var Ce=class{constructor(o,e={setTimeout:(t,i)=>globalThis.setTimeout(t,i),clearTimeout:t=>globalThis.clearTimeout(t)}){this.actions=o;this.timers=e;this._key=null;this._motor=null;this._scopeStops=[];this._remainingStops=[];this._stopTargetGenerations=new Map;this._keyboardKey=null;this._motorId=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0;this._repeatBlocked=!1;this._tapDirection=null;this._leaseOwner=`card-${Math.random().toString(36).slice(2,12)}`;this._started=!1;this._releaseId=0;this._pendingReleases=new Map}get heldKey(){return this._key}start(o,e,t,i,n=i?[i]:[],r=[],a=null,l){if(this._key!==null)return;let p=Array.isArray(n)?n:[];this._target=Array.isArray(n)?l:n,this._flushPendingForTarget(i??o.cover??o.key),this._key=o.key,this._motor=Object.freeze({...o,...o.timedMove?{timedMove:Object.freeze({...o.timedMove})}:{}}),this._motorId=Se(o),this._cover=o.cover??null,this._stop=i??null,this._scopeStops=[...new Set([...p,...i?[i]:[],...o.cover?[o.cover]:[],...this._targetScope(this._target)])],this._remainingStops=[...new Set(r)],this.claimStopScope(this._scopeStops),this._pointerId=t,this._keyboardKey=a;let u=++this._generation;this._heldControl=o.heldControls?.[e]??o.heldControl,this._releaseButton=o.releaseButton;let h=this.actions.lease!==void 0&&Ci(o,e);if(this._heldControl){let g=this._heldControl.startDelayMs;g<=0?this._startHeldControl(this._motor,e,u,h):this._startTimer=this.timers.setTimeout(()=>this._startHeldControl(this._motor??o,e,u,h),g);return}this._started=!0,h?this._leaseHold(this._motor,e,u):this._repeat(this._motor,e,u)}get tapMoving(){return this._tapDirection!==null}tapDirection(o){return this._tapDirection!==null&&this._motorId===Se(o)?this._tapDirection:void 0}tap(o,e,t,i=t?[t]:[],n=[],r){if(this._tapDirection!==null){this.endTap();return}if(this._key!==null||(o.heldControls?.[e]??o.heldControl)&&!(this.actions.lease&&le(o,e))||(this._tapDirection=e,this.start(o,e,null,t,i,n,null,r),this._tapDirection===null))return;let l=this._generation;this._tapTimer=this.timers.setTimeout(()=>{l===this._generation&&this.endTap()},Mi),this.actions.changed?.()}endTap(){this._tapDirection!==null&&this._motor&&this.end(this._motor)}retireTap(){this._tapDirection!==null&&this._reset()}_targetScope(o){if(!o)return[];let e=o.side==="left"||o.side==="right"?[o.side]:["left","right"];return[...new Set([o.deviceId,...o.physicalDeviceId?[o.physicalDeviceId]:[],...o.physicalChildIds??[]])].flatMap(i=>e.map(n=>`target:${i}:${n}`))}claimStopScope(o,e){for(let t of new Set([...o,...this._targetScope(e)]))this._stopTargetGenerations.set(t,(this._stopTargetGenerations.get(t)??0)+1)}_startHeldControl(o,e,t,i){this._startTimer=void 0,!(t!==this._generation||this._motorId!==Se(o))&&(this._started=!0,i&&this._leaseHold(o,e,t))}_leaseHold(o,e,t){let i={owner:this._leaseOwner,generation:t},n=le(o,e),r=!0,a=()=>{r=!1,t===this._generation&&(this._renewTimer!==void 0&&(this.timers.clearTimeout(this._renewTimer),this._renewTimer=void 0),this.retireTap())},l=()=>{a(),!n&&t===this._generation&&this._reset()},p=this.actions.lease?.(o,e,i);if(!p)return;p.then(l,l);let u=()=>{this._renewTimer=void 0,!(!r||t!==this._generation||this._repeatBlocked)&&(this.actions.lease?.(o,e,i)?.catch(a),this._renewTimer=this.timers.setTimeout(u,250))};this._renewTimer=this.timers.setTimeout(u,250)}async _repeat(o,e,t){let i=this._motor;if(i)try{for(;t===this._generation&&!this._repeatBlocked;){let n=this.actions.pulse(i,e);if(!n)return;this._pulseInFlight=n;try{await n}finally{this._pulseInFlight===n&&(this._pulseInFlight=void 0)}}}catch{}finally{t===this._generation&&this.retireTap()}}_targetKey(o=this._stop??void 0,e=this._cover??void 0){return o??e??this._key??""}_release(o){return o.releaseButton?(this.actions.stopBed(o.releaseButton),o.releaseButton):o.cover?(this.actions.stopCover(o.cover,o.stopEntityId),o.cover):(this.actions.stopBed(o.stopEntityId),o.stopEntityId)}_scheduleRelease(){let o={id:++this._releaseId,releaseButton:this._releaseButton,motorKey:this._key??"",targetKey:this._targetKey(),target:this._target,cover:this._cover??void 0,stopEntityId:this._stop??void 0,scopeGenerations:new Map(this._scopeStops.map(t=>[t,this._stopTargetGenerations.get(t)??0]))};this._pendingReleases.set(o.id,o);let e=this._heldControl?.releaseDelayMs??0;if(e<=0){this._runRelease(o);return}o.timer=this.timers.setTimeout(()=>this._runRelease(o),e)}_runRelease(o){if(this._pendingReleases.delete(o.id)&&(o.timer!==void 0&&this.timers.clearTimeout(o.timer),[...o.scopeGenerations].every(([e,t])=>this._stopTargetGenerations.get(e)===t)))return this._release(o)}_flushPendingForTarget(o){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===o&&(this._runRelease(t),e.add(i))}return e}_flushAllReleases(o){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===o?(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer)):(this._runRelease(t),e.add(i))}return e}_targetsOverlap(o,e,t,i){return t!==void 0&&o===t?!0:!!e&&!!i&&Ri(e,i)}_discardReleasesOverlapping(o,e){let t=!1;for(let i of[...this._pendingReleases.values()])!i.scopeGenerations.has(o)&&!this._targetsOverlap(i.targetKey,i.target,o,e)||(this._pendingReleases.delete(i.id),i.timer!==void 0&&this.timers.clearTimeout(i.timer),i.target?.side==="both"&&[...i.scopeGenerations].every(([n,r])=>this._stopTargetGenerations.get(n)===r)&&(t=!0));return t}_discardAllReleases(){for(let o of this._pendingReleases.values())o.timer!==void 0&&this.timers.clearTimeout(o.timer);this._pendingReleases.clear()}endFromPointer(o,e,t,i){this._pointerId===null||e!==this._pointerId||t&&(i!==void 0&&this._stop!==i||this.end(o,i))}endActiveFromPointer(o,e){!this._motor||this._pointerId===null||this.endFromPointer(this._motor,o,e)}endKeyboard(o,e,t){this._pointerId!==null||this._tapDirection!==null||!this._motor||o&&!this._ownsRelease(o,e)||e!==void 0&&this._stop!==e||t!==void 0&&this._keyboardKey!==null&&this._keyboardKey!==t||this.end(this._motor)}end(o,e){if(!this._ownsRelease(o,e))return;let t=this._started,i=this._heldControl!==void 0,n={releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0};t&&i&&this._scheduleRelease(),this._reset(),!(!t||i)&&this._release(n)}_ownsRelease(o,e){return this._key!==o.key?!1:e===void 0?this._motorId===Se(o):this._stop===e}cancel(o,e=!1){if(!o)return!1;let t=this._key===o.key;t&&this._reset();let i=!1;if(e)for(let n of[...this._pendingReleases.values()])n.motorKey===o.key&&(this._pendingReleases.delete(n.id),n.timer!==void 0&&this.timers.clearTimeout(n.timer),i=!0);return t||i}stopCover(o,e,t,i,n=[]){let r=o.cover;if(!r)return;let a=e!==void 0&&e.side!=="both",l=new Set,p=new Map,u,h=b=>{for(let E of b)E!==i&&(l.add(E),p.set(E,this._stopTargetGenerations.get(E)??0))};if(this._key!==null&&(t==="side"||this._key===o.key)&&(r===this._cover||i!==void 0&&this._scopeStops.includes(i)||this._targetsOverlap(this._targetKey(),this._target,r,e))){let b=this._target?.side==="both"&&a||i!==void 0&&this._remainingStops.includes(i);this._started&&b&&(i&&h(this._remainingStops),this._heldControl&&h(n)),u=this._pulseInFlight,b&&!this._heldControl&&l.size===0?this._repeatBlocked=!0:this._reset()}for(let b of[...this._pendingReleases.values()]){let E=b.target?.side==="both"&&b.target.deviceId===e?.deviceId&&(e?.side==="left"||e?.side==="right");t!=="side"&&E||t!=="side"&&b.motorKey!==o.key||!(b.cover===r||i!==void 0&&b.scopeGenerations.has(i)||this._targetsOverlap(b.targetKey,b.target,r,e))||(this._pendingReleases.delete(b.id),b.timer!==void 0&&this.timers.clearTimeout(b.timer),a&&b.target?.side==="both"&&[...b.scopeGenerations].every(([v,k])=>this._stopTargetGenerations.get(v)===k)&&h(n))}let g=this._key!==null?this._stop:null,y=()=>{for(let b of l)b!==g&&(this._stopTargetGenerations.get(b)??0)===p.get(b)&&this.actions.stopBed(b)};u?u.then(y,y):y()}stopAll(o,e,t,i=[]){let n=o??this._stop??void 0,r=this._key!==null&&this._started?{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0}:void 0,a=typeof t=="object"?t:void 0,l=typeof t=="string"?t:void 0,p=[...new Set([...Array.isArray(e)?e:n?[n]:this._scopeStops,...this._targetScope(a),...n?[n]:[]])],u=e===!0&&!a,h=l===void 0||l===this._key||n===this._cover,g=this._key!==null&&h&&(u||p.length===0||this._scopeStops.some(k=>p.includes(k))||this._targetsOverlap(this._targetKey(),this._target,n,a)),y=!1;o!==void 0&&(u?this._discardAllReleases():y=this._discardReleasesOverlapping(o,a)),y||=g&&this._started&&this._heldControl!==void 0&&this._target?.side==="both";let b=[...new Set([...g&&this._started?this._remainingStops:[],...y?i:[]])].filter(k=>!p.includes(k)&&k!==this._stop),E=g?this._pulseInFlight:void 0,v=new Map(b.map(k=>[k,this._stopTargetGenerations.get(k)??0]));if(g&&this._reset(),o===void 0){let k=this._flushAllReleases(),M=r?.stopEntityId??r?.cover;r&&(M===void 0||!k.has(M))?this._release(r):!r&&k.size===0&&this.actions.stopBed(n)}else this.actions.stopBed(o);if(b.length>0){let k=()=>{for(let M of b)(this._stopTargetGenerations.get(M)??0)===v.get(M)&&this.actions.stopBed(M)};E?E.then(k,k):k()}}abandon(){let o=this._key===null?null:{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0},e=this._started;this._reset();let t=new Set,i=n=>{n!==void 0&&t.add(n)};o&&e&&i(this._release(o));for(let n of[...this._pendingReleases.values()])i(this._runRelease(n));return[...t]}releaseOnFocusLoss(){this.abandon()}cancelForStopScope(o){let e=!1;for(let t of[...this._pendingReleases.values()])o.includes(t.targetKey)&&(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer),e=!0);return this._key!==null&&this._scopeStops.some(t=>o.includes(t))&&(this._reset(),e=!0),e}_reset(){this._startTimer!==void 0&&this.timers.clearTimeout(this._startTimer),this._startTimer=void 0,this._renewTimer!==void 0&&this.timers.clearTimeout(this._renewTimer),this._renewTimer=void 0,this._tapTimer!==void 0&&this.timers.clearTimeout(this._tapTimer),this._tapTimer=void 0;let o=this._tapDirection!==null;this._tapDirection=null,this._key=null,this._motor=null,this._scopeStops=[],this._remainingStops=[],this._keyboardKey=null,this._pulseInFlight=void 0,this._motorId=null,this._cover=null,this._stop=null,this._target=void 0,this._pointerId=null,this._repeatBlocked=!1,this._started=!1,this._heldControl=void 0,this._releaseButton=void 0,this._generation++,o&&this.actions.changed?.()}};function Rt(s,o,e){let t=()=>{s.abandon()},i=()=>{o.visibilityState==="hidden"&&t()};return o.addEventListener("visibilitychange",i),e.addEventListener("pagehide",t),()=>{o.removeEventListener("visibilitychange",i),e.removeEventListener("pagehide",t)}}function ce(s,o,e,t,i){s.stopAll(o,e??(o?[o]:void 0),t??ee(i,o),Xe(i,o))}function D(s,o){let e=o?s?.devices[o]:void 0;return(e?.name_by_user||e?.name)?.trim()||void 0}function S(s,o,e=o){let t=s?.states[o];return(t?s.formatEntityName(t,{type:"entity"}):s?.entities[o]?.name)||e}function Bt(s,o){if(!o||s.length<=o.length||!s.toLowerCase().startsWith(o.toLowerCase()))return s;let e=s.slice(o.length);return/^[\s\-·:,]/.test(e)&&e.replace(/^[\s\-·:,]+/,"")||s}var O="adjustable_bed",j=["graphic","motors","firmness","presets","saved_positions","memory","lighting","massage","utility","climate","connection"],Ht=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],Lt=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_reading","preset_swing","preset_incline","preset_both_up","preset_yoga"],Ye=s=>s.split(".",1)[0],Dt=s=>s.translation_key??"";function Bi(s,o){let e=s.states[o]?.attributes,t=e?.card_section;if(typeof t!="string")return;let{card_role:i,card_motor:n,card_slot:r}=e;return{section:t,...typeof i=="string"?{role:i}:{},...typeof n=="string"?{motor:n}:{},...typeof r=="number"?{slot:r}:{}}}var Ot=(s,o)=>s.states[o]?.attributes.bed_side??s.states[o]?.attributes.side;function Hi(){return{motors:[],firmness:[],presets:[],presetSaves:[],memory:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[],utilityStates:[]}}function B(s,o,e){let t=Hi();if(!o||!s?.entities)return t;let i=()=>t.lights.mood??={selects:[],numbers:[]},n=Object.values(s.entities).filter(_=>_.device_id===o&&_.platform===O),r=new Map,a=_=>{let m=r.get(_);return m||(m={key:_},r.set(_,m)),m},l=(_,m,w,x)=>{let $=a(m);$[w]=_;let T=Me(s,_,x??o);T&&($.holdLease=T);let A=s.states[_]?.attributes,Q=A?.held_control,V=A?.hold_start_delay_ms,H=A?.hold_release_delay_ms,F=typeof A?.hold_release_button_key=="string",We=Ae(s,_);typeof Q=="string"&&typeof V=="number"&&Number.isFinite(V)&&V>=0&&typeof H=="number"&&Number.isFinite(H)&&H>=0&&x&&(!F||We)&&A?.requires_confirmation!==!0&&($.deviceId=x,$.holdEntityId=_,We&&($.releaseButton=We),$.heldControls={...$.heldControls,[w]:{control:Q,startDelayMs:V,releaseDelayMs:H}});let Ee=A?.paired_hold_motor;Ee==="back"||Ee==="legs"||Ee==="lumbar"?$.timedMove={deviceId:o,motor:Ee,...A?.paired_hold_side==="both"?{side:"both"}:{}}:(m==="back"||m==="legs"||m==="lumbar")&&typeof Q=="string"&&!F&&A?.timed_move!==!1&&($.timedMove={deviceId:o,motor:m,...A?.bed_side==="both"?{side:"both"}:{}})},p=(_,m,w)=>{let x=a(m);x.cover=_;let $=s.states[_]?.attributes,T=$?.held_control_up,A=$?.held_control_down,Q=Ae(s,_);Q&&(x.releaseButton=Q);let V=Me(s,_,w);if(V&&(x.holdLease=V),($?.held_stop_scope==="motor"||$?.held_stop_scope==="side")&&(x.coverStopScope=$.held_stop_scope),typeof T=="string"&&typeof A=="string"&&(typeof $?.hold_release_button_key!="string"||x.releaseButton)){(m==="back"||m==="legs"||m==="lumbar")&&(x.timedMove={deviceId:o,motor:m});let H=$?.hold_start_delay_ms,F=$?.hold_release_delay_ms;($?.held_stop_scope==="motor"||$?.held_stop_scope==="side")&&w&&typeof H=="number"&&Number.isFinite(H)&&H>=0&&typeof F=="number"&&Number.isFinite(F)&&F>=0&&(x.deviceId=w,x.holdEntityId=_,x.heldControls={up:{control:T,startDelayMs:H,releaseDelayMs:F},down:{control:A,startDelayMs:H,releaseDelayMs:F}})}},u=new Map,h=_=>{let m=u.get(_);return m||(m={slot:_},u.set(_,m)),m},g=t.lights,y=(_,m,w)=>_===void 0?m:m<_?(w(_),m):(w(m),_),b=(_,m)=>{m==="switch"?(g.switches??=[]).push(_):m==="number"?(g.numbers??=[]).push(_):m==="button"?(g.buttons??=[]).push(_):(g.states??=[]).push(_)},E=(_,m)=>(g[_]=y(g[_],m,w=>b(w,Ye(w))),g[_]===m),v=(_,m)=>{m==="button"?t.massage.buttons.push(_):m==="number"?t.massage.numbers.push(_):m==="select"?(t.massage.selects??=[]).push(_):m==="switch"?(t.massage.switches??=[]).push(_):(t.massage.states??=[]).push(_)},k=(_,m)=>{m==="number"?(t.utilityNumbers??=[]).push(_):m==="select"?(t.utilitySelects??=[]).push(_):m==="sensor"||m==="binary_sensor"?(t.utilityStates??=[]).push(_):m==="switch"?(t.utilitySwitches??=[]).push(_):t.utility.push(_)},M=[],$t=[];for(let _ of n){let m=_.entity_id,w=Bi(s,m);if(!w||w.section==="hidden"||_.hidden&&!(w.section==="motors"&&w.role==="stop")||e&&Ot(s,m)!==e)continue;let x=Ye(m),{role:$}=w;switch(w.section){case"motors":if($==="stop")t.stop=y(t.stop,m,T=>(t.extraStops??=[]).push(T));else if(x==="switch"||x==="select"){let T=x==="switch"?"synchro":"controlSide";t[T]=y(t[T],m,A=>(t.motorExtras??=[]).push(A))}else{if(w.motor===void 0)break;x==="cover"?p(m,w.motor,_.device_id):$==="up"||$==="down"?l(m,w.motor,$,_.device_id):$==="reference"?a(w.motor).reference=m:$==="estimate"?a(w.motor).estimate=m:x==="sensor"&&$!=="position"?a(w.motor).angle=m:a(w.motor).position=m}break;case"firmness":t.firmness.push(m);break;case"presets":($==="save"?$t:M).push({key:Dt(_),id:m});break;case"memory":if(w.slot===void 0)break;$==="save"?h(w.slot).save=m:h(w.slot).goto=m;break;case"saved_positions":x==="button"?t.estimateRemote=m:t.savedPositions=m;break;case"connection":$==="connect"?t.connect=m:$==="disconnect"?t.disconnect=m:t.connectivity=m;break;case"lighting":switch($){case"state":E("state",m);break;case"level":E("level",m);break;case"toggle":E("toggle",m);break;case"cycle":E("cycle",m);break;case"timer":E("timer",m);break;case"timer_minutes":E("timerMinutes",m)&&(g.timerAppliesImmediately=!0);break;case"pending_timer_minutes":E("timerMinutes",m)&&(g.timerAppliesImmediately=!1);break;case"timer_toggle":E("timerToggle",m);break;case"mood_toggle":i().toggle=y(i().toggle,m,T=>(i().buttons??=[]).push(T));break;case"mood":x==="select"?i().selects.push(m):x==="number"?i().numbers.push(m):(i().buttons??=[]).push(m);break;default:x==="light"?E("light",m):x==="switch"&&Dt(_)==="under_bed_lights"?E("switch",m):x==="binary_sensor"?E("state",m):x==="select"?E("timer",m):b(m,x)}break;case"massage":$==="timer"&&x!=="button"?t.massage.timer=y(t.massage.timer,m,T=>v(T,Ye(T))):v(m,x);break;case"climate":x==="select"?t.climate.selects.push(m):x==="number"?t.climate.numbers.push(m):t.climate.entities.push(m);break;case"utility":k(m,x);break}}let ki=[...r.keys()],Ei=[...Ht.filter(_=>r.has(_)),...ki.filter(_=>!Ht.includes(_)).sort()];t.motors=Ei.map(_=>r.get(_)).filter(_=>_.cover||_.up||_.down||_.angle||_.position),!g.light&&!g.switch&&g.switches?.length===1&&(g.switch=g.switches[0],g.switches=void 0);let xt=_=>{let m=Lt.indexOf(_);return m<0?Lt.length:m},kt=_=>_.sort((m,w)=>xt(m.key)-xt(w.key)||(m.key<w.key?-1:m.key>w.key?1:0)||(m.id<w.id?-1:m.id>w.id?1:0)).map(m=>m.id);return t.presets=kt(M),t.presetSaves=kt($t),t.memory=[...u.values()].filter(_=>_.goto||_.save).sort((_,m)=>_.slot-m.slot),t}function Pe(s,o){return!o||!s?.entities?!1:Object.values(s.entities).some(e=>e.device_id===o&&e.platform===O&&s.states[e.entity_id]?.attributes.bed_side==="both")}function de(s,o){if(!o||!s?.devices)return[];let e=i=>(D(s,i)??i).toLowerCase(),t=i=>{for(let n of Object.values(s.entities??{})){if(n.device_id!==i||n.platform!=="adjustable_bed")continue;let r=Ot(s,n.entity_id);if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(s.devices).filter(i=>(i.parent_device_id??i.via_device_id)===o).map(i=>i.id).sort((i,n)=>t(i)-t(n)||e(i).localeCompare(e(n)))}function Re(s,o){if(!o||!s?.devices)return o;let e=s.devices[o]?.parent_device_id??s.devices[o]?.via_device_id;return e&&s.devices[e]&&de(s,e).length?e:o}function G(s){let o=s.lights;return s.motors.length===0&&!s.synchro&&!s.controlSide&&s.firmness.length===0&&s.presets.length===0&&s.presetSaves.length===0&&s.memory.length===0&&!s.stop&&!s.extraStops?.length&&!s.motorExtras?.length&&!s.connect&&!s.disconnect&&!s.connectivity&&!pe(o)&&!o.state&&s.massage.buttons.length===0&&s.massage.numbers.length===0&&!s.massage.selects?.length&&!s.massage.states?.length&&!s.massage.switches?.length&&!s.massage.timer&&s.climate.entities.length===0&&s.climate.selects.length===0&&s.climate.numbers.length===0&&s.utility.length===0&&!s.utilityNumbers?.length&&!s.utilitySelects?.length&&!s.utilityStates?.length&&!s.utilitySwitches?.length&&!s.savedPositions}function pe(s){return!!(s.light||s.switch||s.switches?.length||s.level||s.toggle||s.numbers?.length||s.buttons?.length||s.states?.length||s.cycle||s.timer||s.timerMinutes||s.timerToggle||s.mood?.toggle||s.mood?.selects.length||s.mood?.numbers.length||s.mood?.buttons?.length)}function te(s,o){for(let e of s.motors)e.cover||(e.nameFrom=o.flatMap(t=>t.motors).find(t=>t.key===e.key&&t.cover)?.cover)}var jt={"action.on":"On","action.off":"Off","action.close":"Close","action.confirm":"{action}? This replaces the saved preset.","action.confirm_send":"Send {action} to the bed?","editor.open_dialog":"Open full card in a dialog","editor.show_percentage_graphic":"Draw percentage positions (schematic)","editor.show_lumbar_graphic":"Show a separate lumbar section","editor.show_graphic_labels":"Show labels beneath the graphic","section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.stop":"Stop","action.stop_all":"Stop all","tap.moving_up":"Moving up \xB7 tap to stop","tap.moving_down":"Moving down \xB7 tap to stop","motor.tv_lift":"TV lift","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","motor.head_feet":"Head and feet","motor.both":"Back and legs","motor.all_motors":"All motors","motor.waist":"Waist","motor.head_tilt":"Head tilt","motor.headrest":"Headrest","motor.mid_body":"Mid-body","motor.t_flat":"T-flat","motor.main_motor":"Main motor","motor.storage_lift":"Storage lift","motor.extra":"Extra motor","motor.upper_section":"Upper section","motor.lower_section":"Lower section","motor.lounge":"Lounge","motor.zero_gravity":"Zero gravity","motor.lumbar_pillow":"Lumbar and pillow","motor.pillow_lumbar_tilt":"Pillow and lumbar tilt","motor.pillow_2":"Pillow 2","motor.motor_1":"Motor 1","motor.motor_2":"Motor 2","motor.motor_3":"Motor 3","motor.motor_4":"Motor 4","motor.motor_5":"Motor 5","motor.motor_6":"Motor 6","motor.motor_7":"Motor 7","motor.motors_1_2":"Motors 1 and 2","motor.motors_2_3":"Motors 2 and 3","motor.motors_3_4":"Motors 3 and 4","motor.control_1":"Control 1","motor.control_2":"Control 2","motor.control_3":"Control 3","motor.control_4":"Control 4","motor.control_5":"Control 5","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle, reconnects when needed","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.device_missing":"This bed is no longer in Home Assistant. Pick the bed again in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.motors_group":"Motors","editor.tap_to_move":"Tap to start and stop movement","editor.tap_to_move_hint":"Tap an arrow to start. Tap any arrow or Stop to end. Movement stops by itself after at most 30 seconds.","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Side","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"Glance only","editor.recipe_quick":"Quick actions","editor.recipe_controls":"Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Side to control","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both","section.saved_positions":"Saved positions","editor.show_saved_positions":"Saved positions","estimate.readout":"\u2248 {percent}%","estimate.readout_was":"Was \u2248 {percent}%","estimate.unknown":"Unknown","estimate.not_calibrated":"Not calibrated","estimate.chip_estimated":"Estimated","estimate.chip_unconfirmed":"Unconfirmed","estimate.chip_unknown":"Unknown","estimate.alert_calibrate":"Estimated positions are on but not calibrated yet.","estimate.calibrate_now":"Calibrate now","estimate.alert_unconfirmed":"Position unconfirmed after restart. Last estimate: {values}. Saved positions are paused until you confirm.","estimate.alert_unknown":"Position unknown: {reason}. Saved positions are paused until you set the reference.","estimate.reason_not_referenced":"no reference is set yet","estimate.reason_restart":"Home Assistant restarted","estimate.reason_failed_move":"a movement failed","estimate.reason_untracked_move":"the bed moved in a way that is not timed","estimate.reason_hardware_preset":"a hardware preset or memory moved the bed","estimate.reason_remote":"you reported using the remote","estimate.reason_connection_lost":"the connection dropped during a movement","estimate.unchanged":"It hasn't moved","estimate.set_reference":"Set reference\u2026","estimate.edit":"Edit","estimate.done":"Done","estimate.edit_hint":"Tap a position to rename, update or delete it.","estimate.save":"Save\u2026","estimate.footer":"Estimated from movement time. Remote use is not seen.","estimate.scope_both":"Both sides","estimate.scope_left":"Left only","estimate.scope_right":"Right only","estimate.recalled":"Moved to {name} (estimated)","estimate.ref_title":"Set reference","estimate.ref_text":"Choose how to get a known position. The bed never moves on its own to recover.","estimate.ref_lowering":"The lowering has finished. Check that the motors are fully lowered, then confirm.","estimate.ref_flat":"Fully lowered now","estimate.ref_flat_detail":"{motors} are fully down. Sets them to 0%.","estimate.ref_lower":"Lower fully, then I confirm","estimate.ref_lower_detail":"Moves down for the full travel time plus a margin. You confirm it is fully lowered afterwards.","estimate.ref_only":"Only the {motor}","estimate.ref_only_detail":"The other motors keep their estimate.","estimate.ref_lower_start":"Lower","estimate.ref_confirm":"Confirm fully lowered","estimate.save_title":"Save current position","estimate.name":"Name","estimate.create_button":"Also create a button entity","estimate.create_button_detail":"For automations and voice.","estimate.save_note":"Recall moves each motor for the calculated time. Expect a few percent difference.","estimate.save_confirm":"Save","estimate.edit_title":'Edit "{name}"',"estimate.saved":"Saved","estimate.now":"Now","estimate.update_blocked":'"Update to current" needs every side it covers confirmed. Set a reference first.',"estimate.delete":"Delete","estimate.update":"Update to current","estimate.ref_lowering_running":"The bed is lowering past its full travel time. Wait until it has stopped, or press Stop.","editor.configure_dialog":"Configure dialog full card","editor.dialog_configuration":"Dialog full card","editor.dialog_configuration_hint":"These full-card settings apply only inside the dialog. The compact card keeps its own settings.","editor.back_to_compact":"Back to compact configuration","compact.target_fixed":"Controls: {side}","estimate.ref_flat_detail_one":"{motors} is fully down. Sets it to 0%.","action.motor_up":"{motor} up","action.motor_down":"{motor} down","action.motor_stop":"Stop {motor}","card.memory_slot":"Memory {slot}","card.picker_name":"Adjustable Bed Card","card.picker_description":"Control an adjustable bed: position, presets, memory, lighting and massage.","editor.graphic_group":"Bed graphic"};var zt={"action.on":"P\xE5","action.off":"Av","action.close":"Lukk","action.confirm":"{action}? Dette erstatter den lagrede posisjonen.","action.confirm_send":"Vil du sende {action} til sengen?","editor.open_dialog":"\xC5pne hele kortet i en dialog","editor.show_percentage_graphic":"Vis prosentposisjoner (skjematisk)","editor.show_lumbar_graphic":"Vis en egen korsryggseksjon","editor.show_graphic_labels":"Vis etiketter under grafikken","section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.stop":"Stopp","action.stop_all":"Stopp alt","tap.moving_up":"Beveger seg opp \xB7 trykk for \xE5 stoppe","tap.moving_down":"Beveger seg ned \xB7 trykk for \xE5 stoppe","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","motor.head_feet":"Hode og f\xF8tter","motor.both":"Rygg og ben","motor.all_motors":"Alle motorer","motor.waist":"Midje","motor.head_tilt":"Hodevipp","motor.headrest":"Hodest\xF8tte","motor.mid_body":"Midtparti","motor.t_flat":"T-flat","motor.main_motor":"Hovedmotor","motor.storage_lift":"Oppbevaringsl\xF8ft","motor.extra":"Ekstra motor","motor.upper_section":"\xD8vre del","motor.lower_section":"Nedre del","motor.lounge":"Lounge","motor.zero_gravity":"Nullgravitasjon","motor.lumbar_pillow":"Korsrygg og pute","motor.pillow_lumbar_tilt":"Pute- og korsryggvipp","motor.pillow_2":"Pute 2","motor.motor_1":"Motor 1","motor.motor_2":"Motor 2","motor.motor_3":"Motor 3","motor.motor_4":"Motor 4","motor.motor_5":"Motor 5","motor.motor_6":"Motor 6","motor.motor_7":"Motor 7","motor.motors_1_2":"Motor 1 og 2","motor.motors_2_3":"Motor 2 og 3","motor.motors_3_4":"Motor 3 og 4","motor.control_1":"Kontroll 1","motor.control_2":"Kontroll 2","motor.control_3":"Kontroll 3","motor.control_4":"Kontroll 4","motor.control_5":"Kontroll 5","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus, kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.device_missing":"Denne sengen finnes ikke lenger i Home Assistant. Velg sengen p\xE5 nytt i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.motors_group":"Motorer","editor.tap_to_move":"Trykk for \xE5 starte og stoppe bevegelse","editor.tap_to_move_hint":"Trykk p\xE5 en pil for \xE5 starte. Trykk p\xE5 en pil eller Stopp for \xE5 avslutte. Bevegelsen stopper av seg selv etter maks 30 sekunder.","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Side","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"Kun oversikt","editor.recipe_quick":"Hurtighandlinger","editor.recipe_controls":"Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Side som styres","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge","section.saved_positions":"Lagrede posisjoner","editor.show_saved_positions":"Lagrede posisjoner","estimate.readout":"\u2248 {percent} %","estimate.readout_was":"Var \u2248 {percent} %","estimate.unknown":"Ukjent","estimate.not_calibrated":"Ikke kalibrert","estimate.chip_estimated":"Ansl\xE5tt","estimate.chip_unconfirmed":"Ubekreftet","estimate.chip_unknown":"Ukjent","estimate.alert_calibrate":"Ansl\xE5tte posisjoner er sl\xE5tt p\xE5, men ikke kalibrert enn\xE5.","estimate.calibrate_now":"Kalibrer n\xE5","estimate.alert_unconfirmed":"Posisjonen er ubekreftet etter omstart. Siste anslag: {values}. Lagrede posisjoner er satt p\xE5 pause til du bekrefter.","estimate.alert_unknown":"Posisjonen er ukjent: {reason}. Lagrede posisjoner er satt p\xE5 pause til du setter referansen.","estimate.reason_not_referenced":"ingen referanse er satt enn\xE5","estimate.reason_restart":"Home Assistant startet p\xE5 nytt","estimate.reason_failed_move":"en bevegelse mislyktes","estimate.reason_untracked_move":"sengen beveget seg uten tidtaking","estimate.reason_hardware_preset":"en forh\xE5ndsinnstilling eller et minne i sengen flyttet den","estimate.reason_remote":"du meldte at fjernkontrollen ble brukt","estimate.reason_connection_lost":"forbindelsen falt ut under en bevegelse","estimate.unchanged":"Den har ikke flyttet seg","estimate.set_reference":"Sett referanse\u2026","estimate.edit":"Rediger","estimate.done":"Ferdig","estimate.edit_hint":"Trykk p\xE5 en posisjon for \xE5 gi den nytt navn, oppdatere eller slette den.","estimate.save":"Lagre\u2026","estimate.footer":"Ansl\xE5tt fra bevegelsestid. Bruk av fjernkontrollen registreres ikke.","estimate.scope_both":"Begge sider","estimate.scope_left":"Bare venstre","estimate.scope_right":"Bare h\xF8yre","estimate.recalled":"Flyttet til {name} (ansl\xE5tt)","estimate.ref_title":"Sett referanse","estimate.ref_text":"Velg hvordan du f\xE5r en kjent posisjon. Sengen flytter seg aldri av seg selv for \xE5 finne den igjen.","estimate.ref_lowering":"Senkingen er ferdig. Sjekk at sengen ligger helt flatt, og bekreft.","estimate.ref_flat":"Sengen er flat n\xE5","estimate.ref_flat_detail":"{motors} er helt nede. Setter dem til 0 %.","estimate.ref_lower":"Senk til flat, s\xE5 bekrefter jeg","estimate.ref_lower_detail":"Senker i hele bevegelsestiden pluss en margin. Du bekrefter etterp\xE5 at den er flat.","estimate.ref_only":"Bare {motor}","estimate.ref_only_detail":"De andre motorene beholder anslaget sitt.","estimate.ref_lower_start":"Senk","estimate.ref_confirm":"Bekreft flat","estimate.save_title":"Lagre n\xE5v\xE6rende posisjon","estimate.name":"Navn","estimate.create_button":"Lag ogs\xE5 en knappeentitet","estimate.create_button_detail":"For automasjoner og tale.","estimate.save_note":"Henting flytter hver motor i den beregnede tiden. Regn med noen prosent avvik.","estimate.save_confirm":"Lagre","estimate.edit_title":"Rediger \xAB{name}\xBB","estimate.saved":"Lagret","estimate.now":"N\xE5","estimate.update_blocked":"\xABOppdater til n\xE5v\xE6rende\xBB krever at alle sidene den dekker er bekreftet. Sett en referanse f\xF8rst.","estimate.delete":"Slett","estimate.update":"Oppdater til n\xE5v\xE6rende","estimate.ref_lowering_running":"Sengen senkes lenger enn hele bevegelsestiden. Vent til den har stoppet, eller trykk Stopp.","editor.configure_dialog":"Konfigurer fullt kort i dialogen","editor.dialog_configuration":"Fullt kort i dialogen","editor.dialog_configuration_hint":"Disse innstillingene gjelder bare det fulle kortet i dialogen. Det kompakte kortet beholder sine egne innstillinger.","editor.back_to_compact":"Tilbake til kompakt konfigurasjon","compact.target_fixed":"Styrer: {side}","estimate.ref_flat_detail_one":"{motors} er helt nede. Setter den til 0 %.","action.motor_up":"{motor} opp","action.motor_down":"{motor} ned","action.motor_stop":"Stopp {motor}","card.memory_slot":"Minne {slot}","card.picker_name":"Adjustable Bed-kort","card.picker_description":"Styr en justerbar seng: posisjon, forh\xE5ndsvalg, minne, lys og massasje.","motor.tv_lift":"TV-heis","editor.graphic_group":"Sengegrafikk"};var W={en:jt,nb:zt};function Oi(s){let o=(s||"en").toLowerCase(),e=o.split("-")[0];return W[o]?W[o]:W[e]?W[e]:e==="nn"||e==="no"?W.nb:W.en}function f(s,o,e){return Be(s?.locale?.language||s?.language,o,e)}function Be(s,o,e){let i=Oi(s)[o]??W.en[o]??o;if(e)for(let[n,r]of Object.entries(e))i=i.replace(`{${n}}`,r);return i}var Ze="adjustable-bed-card";function ji(){return typeof document<"u"?document.documentElement.lang||navigator.language:void 0}var Nt=s=>({type:Ze,name:Be(s,"card.picker_name"),description:Be(s,"card.picker_description"),preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(o,e)=>{let t=o.entities[e];return t?.platform!==O||!t.device_id?null:{config:{type:`custom:${Ze}`,device_id:t.device_id}}}});function zi(s,o=ji()){let e=s.customCards??=[],t=e.findIndex(i=>i.type===Ze);t===-1?e.push(Nt(o)):e[t]=Nt(o)}function He(s,o,e=window.customElements){e.get(s)||e.define(s,o)}typeof window<"u"&&zi(window);var Le=globalThis,De=Le.ShadowRoot&&(Le.ShadyCSS===void 0||Le.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Je=Symbol(),Ft=new WeakMap,he=class{constructor(o,e,t){if(this._$cssResult$=!0,t!==Je)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=o,this.t=e}get styleSheet(){let o=this.o,e=this.t;if(De&&o===void 0){let t=e!==void 0&&e.length===1;t&&(o=Ft.get(e)),o===void 0&&((this.o=o=new CSSStyleSheet).replaceSync(this.cssText),t&&Ft.set(e,o))}return o}toString(){return this.cssText}},Gt=s=>new he(typeof s=="string"?s:s+"",void 0,Je),ue=(s,...o)=>{let e=s.length===1?s[0]:o.reduce((t,i,n)=>t+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+s[n+1],s[0]);return new he(e,s,Je)},Kt=(s,o)=>{if(De)s.adoptedStyleSheets=o.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of o){let t=document.createElement("style"),i=Le.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,s.appendChild(t)}},Qe=De?s=>s:s=>s instanceof CSSStyleSheet?(o=>{let e="";for(let t of o.cssRules)e+=t.cssText;return Gt(e)})(s):s;var{is:Ni,defineProperty:Fi,getOwnPropertyDescriptor:Gi,getOwnPropertyNames:Ki,getOwnPropertySymbols:Ii,getPrototypeOf:Ui}=Object,Oe=globalThis,It=Oe.trustedTypes,Vi=It?It.emptyScript:"",Wi=Oe.reactiveElementPolyfillSupport,me=(s,o)=>s,ge={toAttribute(s,o){switch(o){case Boolean:s=s?Vi:null;break;case Object:case Array:s=s==null?s:JSON.stringify(s)}return s},fromAttribute(s,o){let e=s;switch(o){case Boolean:e=s!==null;break;case Number:e=s===null?null:Number(s);break;case Object:case Array:try{e=JSON.parse(s)}catch{e=null}}return e}},je=(s,o)=>!Ni(s,o),Ut={attribute:!0,type:String,converter:ge,reflect:!1,useDefault:!1,hasChanged:je};Symbol.metadata??=Symbol("metadata"),Oe.litPropertyMetadata??=new WeakMap;var z=class extends HTMLElement{static addInitializer(o){this._$Ei(),(this.l??=[]).push(o)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(o,e=Ut){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(o)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(o,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(o,t,e);i!==void 0&&Fi(this.prototype,o,i)}}static getPropertyDescriptor(o,e,t){let{get:i,set:n}=Gi(this.prototype,o)??{get(){return this[e]},set(r){this[e]=r}};return{get:i,set(r){let a=i?.call(this);n?.call(this,r),this.requestUpdate(o,a,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(o){return this.elementProperties.get(o)??Ut}static _$Ei(){if(this.hasOwnProperty(me("elementProperties")))return;let o=Ui(this);o.finalize(),o.l!==void 0&&(this.l=[...o.l]),this.elementProperties=new Map(o.elementProperties)}static finalize(){if(this.hasOwnProperty(me("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(me("properties"))){let e=this.properties,t=[...Ki(e),...Ii(e)];for(let i of t)this.createProperty(i,e[i])}let o=this[Symbol.metadata];if(o!==null){let e=litPropertyMetadata.get(o);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(o){let e=[];if(Array.isArray(o)){let t=new Set(o.flat(1/0).reverse());for(let i of t)e.unshift(Qe(i))}else o!==void 0&&e.push(Qe(o));return e}static _$Eu(o,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof o=="string"?o.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(o=>this.enableUpdating=o),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(o=>o(this))}addController(o){(this._$EO??=new Set).add(o),this.renderRoot!==void 0&&this.isConnected&&o.hostConnected?.()}removeController(o){this._$EO?.delete(o)}_$E_(){let o=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(o.set(t,this[t]),delete this[t]);o.size>0&&(this._$Ep=o)}createRenderRoot(){let o=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Kt(o,this.constructor.elementStyles),o}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(o=>o.hostConnected?.())}enableUpdating(o){}disconnectedCallback(){this._$EO?.forEach(o=>o.hostDisconnected?.())}attributeChangedCallback(o,e,t){this._$AK(o,t)}_$ET(o,e){let t=this.constructor.elementProperties.get(o),i=this.constructor._$Eu(o,t);if(i!==void 0&&t.reflect===!0){let n=(t.converter?.toAttribute!==void 0?t.converter:ge).toAttribute(e,t.type);this._$Em=o,n==null?this.removeAttribute(i):this.setAttribute(i,n),this._$Em=null}}_$AK(o,e){let t=this.constructor,i=t._$Eh.get(o);if(i!==void 0&&this._$Em!==i){let n=t.getPropertyOptions(i),r=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:ge;this._$Em=i;let a=r.fromAttribute(e,n.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(o,e,t,i=!1,n){if(o!==void 0){let r=this.constructor;if(i===!1&&(n=this[o]),t??=r.getPropertyOptions(o),!((t.hasChanged??je)(n,e)||t.useDefault&&t.reflect&&n===this._$Ej?.get(o)&&!this.hasAttribute(r._$Eu(o,t))))return;this.C(o,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(o,e,{useDefault:t,reflect:i,wrapped:n},r){t&&!(this._$Ej??=new Map).has(o)&&(this._$Ej.set(o,r??e??this[o]),n!==!0||r!==void 0)||(this._$AL.has(o)||(this.hasUpdated||t||(e=void 0),this._$AL.set(o,e)),i===!0&&this._$Em!==o&&(this._$Eq??=new Set).add(o))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let o=this.scheduleUpdate();return o!=null&&await o,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,n]of this._$Ep)this[i]=n;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,n]of t){let{wrapped:r}=n,a=this[i];r!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,n,a)}}let o=!1,e=this._$AL;try{o=this.shouldUpdate(e),o?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw o=!1,this._$EM(),t}o&&this._$AE(e)}willUpdate(o){}_$AE(o){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(o)),this.updated(o)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(o){return!0}update(o){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(o){}firstUpdated(o){}};z.elementStyles=[],z.shadowRootOptions={mode:"open"},z[me("elementProperties")]=new Map,z[me("finalized")]=new Map,Wi?.({ReactiveElement:z}),(Oe.reactiveElementVersions??=[]).push("2.1.2");var rt=globalThis,Vt=s=>s,ze=rt.trustedTypes,Wt=ze?ze.createPolicy("lit-html",{createHTML:s=>s}):void 0,Qt="$lit$",K=`lit$${Math.random().toFixed(9).slice(2)}$`,ei="?"+K,qi=`<${ei}>`,Y=document,_e=()=>Y.createComment(""),ve=s=>s===null||typeof s!="object"&&typeof s!="function",at=Array.isArray,Xi=s=>at(s)||typeof s?.[Symbol.iterator]=="function",et=`[ \t
\f\r]`,fe=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,qt=/-->/g,Xt=/>/g,q=RegExp(`>|${et}(?:([^\\s"'>=/]+)(${et}*=${et}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),Yt=/'/g,Zt=/"/g,ti=/^(?:script|style|textarea|title)$/i,lt=s=>(o,...e)=>({_$litType$:s,strings:o,values:e}),d=lt(1),N=lt(2),ko=lt(3),Z=Symbol.for("lit-noChange"),c=Symbol.for("lit-nothing"),Jt=new WeakMap,X=Y.createTreeWalker(Y,129);function ii(s,o){if(!at(s)||!s.hasOwnProperty("raw"))throw Error("invalid template strings array");return Wt!==void 0?Wt.createHTML(o):o}var Yi=(s,o)=>{let e=s.length-1,t=[],i,n=o===2?"<svg>":o===3?"<math>":"",r=fe;for(let a=0;a<e;a++){let l=s[a],p,u,h=-1,g=0;for(;g<l.length&&(r.lastIndex=g,u=r.exec(l),u!==null);)g=r.lastIndex,r===fe?u[1]==="!--"?r=qt:u[1]!==void 0?r=Xt:u[2]!==void 0?(ti.test(u[2])&&(i=RegExp("</"+u[2],"g")),r=q):u[3]!==void 0&&(r=q):r===q?u[0]===">"?(r=i??fe,h=-1):u[1]===void 0?h=-2:(h=r.lastIndex-u[2].length,p=u[1],r=u[3]===void 0?q:u[3]==='"'?Zt:Yt):r===Zt||r===Yt?r=q:r===qt||r===Xt?r=fe:(r=q,i=void 0);let y=r===q&&s[a+1].startsWith("/>")?" ":"";n+=r===fe?l+qi:h>=0?(t.push(p),l.slice(0,h)+Qt+l.slice(h)+K+y):l+K+(h===-2?a:y)}return[ii(s,n+(s[e]||"<?>")+(o===2?"</svg>":o===3?"</math>":"")),t]},be=class s{constructor({strings:o,_$litType$:e},t){let i;this.parts=[];let n=0,r=0,a=o.length-1,l=this.parts,[p,u]=Yi(o,e);if(this.el=s.createElement(p,t),X.currentNode=this.el.content,e===2||e===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(i=X.nextNode())!==null&&l.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let h of i.getAttributeNames())if(h.endsWith(Qt)){let g=u[r++],y=i.getAttribute(h).split(K),b=/([.?@])?(.*)/.exec(g);l.push({type:1,index:n,name:b[2],strings:y,ctor:b[1]==="."?it:b[1]==="?"?ot:b[1]==="@"?st:oe}),i.removeAttribute(h)}else h.startsWith(K)&&(l.push({type:6,index:n}),i.removeAttribute(h));if(ti.test(i.tagName)){let h=i.textContent.split(K),g=h.length-1;if(g>0){i.textContent=ze?ze.emptyScript:"";for(let y=0;y<g;y++)i.append(h[y],_e()),X.nextNode(),l.push({type:2,index:++n});i.append(h[g],_e())}}}else if(i.nodeType===8)if(i.data===ei)l.push({type:2,index:n});else{let h=-1;for(;(h=i.data.indexOf(K,h+1))!==-1;)l.push({type:7,index:n}),h+=K.length-1}n++}}static createElement(o,e){let t=Y.createElement("template");return t.innerHTML=o,t}};function ie(s,o,e=s,t){if(o===Z)return o;let i=t!==void 0?e._$Co?.[t]:e._$Cl,n=ve(o)?void 0:o._$litDirective$;return i?.constructor!==n&&(i?._$AO?.(!1),n===void 0?i=void 0:(i=new n(s),i._$AT(s,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(o=ie(s,i._$AS(s,o.values),i,t)),o}var tt=class{constructor(o,e){this._$AV=[],this._$AN=void 0,this._$AD=o,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(o){let{el:{content:e},parts:t}=this._$AD,i=(o?.creationScope??Y).importNode(e,!0);X.currentNode=i;let n=X.nextNode(),r=0,a=0,l=t[0];for(;l!==void 0;){if(r===l.index){let p;l.type===2?p=new ye(n,n.nextSibling,this,o):l.type===1?p=new l.ctor(n,l.name,l.strings,this,o):l.type===6&&(p=new nt(n,this,o)),this._$AV.push(p),l=t[++a]}r!==l?.index&&(n=X.nextNode(),r++)}return X.currentNode=Y,i}p(o){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(o,t,e),e+=t.strings.length-2):t._$AI(o[e])),e++}},ye=class s{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(o,e,t,i){this.type=2,this._$AH=c,this._$AN=void 0,this._$AA=o,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let o=this._$AA.parentNode,e=this._$AM;return e!==void 0&&o?.nodeType===11&&(o=e.parentNode),o}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(o,e=this){o=ie(this,o,e),ve(o)?o===c||o==null||o===""?(this._$AH!==c&&this._$AR(),this._$AH=c):o!==this._$AH&&o!==Z&&this._(o):o._$litType$!==void 0?this.$(o):o.nodeType!==void 0?this.T(o):Xi(o)?this.k(o):this._(o)}O(o){return this._$AA.parentNode.insertBefore(o,this._$AB)}T(o){this._$AH!==o&&(this._$AR(),this._$AH=this.O(o))}_(o){this._$AH!==c&&ve(this._$AH)?this._$AA.nextSibling.data=o:this.T(Y.createTextNode(o)),this._$AH=o}$(o){let{values:e,_$litType$:t}=o,i=typeof t=="number"?this._$AC(o):(t.el===void 0&&(t.el=be.createElement(ii(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let n=new tt(i,this),r=n.u(this.options);n.p(e),this.T(r),this._$AH=n}}_$AC(o){let e=Jt.get(o.strings);return e===void 0&&Jt.set(o.strings,e=new be(o)),e}k(o){at(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let n of o)i===e.length?e.push(t=new s(this.O(_e()),this.O(_e()),this,this.options)):t=e[i],t._$AI(n),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(o=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);o!==this._$AB;){let t=Vt(o).nextSibling;Vt(o).remove(),o=t}}setConnected(o){this._$AM===void 0&&(this._$Cv=o,this._$AP?.(o))}},oe=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(o,e,t,i,n){this.type=1,this._$AH=c,this._$AN=void 0,this.element=o,this.name=e,this._$AM=i,this.options=n,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=c}_$AI(o,e=this,t,i){let n=this.strings,r=!1;if(n===void 0)o=ie(this,o,e,0),r=!ve(o)||o!==this._$AH&&o!==Z,r&&(this._$AH=o);else{let a=o,l,p;for(o=n[0],l=0;l<n.length-1;l++)p=ie(this,a[t+l],e,l),p===Z&&(p=this._$AH[l]),r||=!ve(p)||p!==this._$AH[l],p===c?o=c:o!==c&&(o+=(p??"")+n[l+1]),this._$AH[l]=p}r&&!i&&this.j(o)}j(o){o===c?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,o??"")}},it=class extends oe{constructor(){super(...arguments),this.type=3}j(o){this.element[this.name]=o===c?void 0:o}},ot=class extends oe{constructor(){super(...arguments),this.type=4}j(o){this.element.toggleAttribute(this.name,!!o&&o!==c)}},st=class extends oe{constructor(o,e,t,i,n){super(o,e,t,i,n),this.type=5}_$AI(o,e=this){if((o=ie(this,o,e,0)??c)===Z)return;let t=this._$AH,i=o===c&&t!==c||o.capture!==t.capture||o.once!==t.once||o.passive!==t.passive,n=o!==c&&(t===c||i);i&&this.element.removeEventListener(this.name,this,t),n&&this.element.addEventListener(this.name,this,o),this._$AH=o}handleEvent(o){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,o):this._$AH.handleEvent(o)}},nt=class{constructor(o,e,t){this.element=o,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(o){ie(this,o)}};var Zi=rt.litHtmlPolyfillSupport;Zi?.(be,ye),(rt.litHtmlVersions??=[]).push("3.3.3");var oi=(s,o,e)=>{let t=e?.renderBefore??o,i=t._$litPart$;if(i===void 0){let n=e?.renderBefore??null;t._$litPart$=i=new ye(o.insertBefore(_e(),n),n,void 0,e??{})}return i._$AI(s),i};var ct=globalThis,L=class extends z{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let o=super.createRenderRoot();return this.renderOptions.renderBefore??=o.firstChild,o}update(o){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(o),this._$Do=oi(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return Z}};L._$litElement$=!0,L.finalized=!0,ct.litElementHydrateSupport?.({LitElement:L});var Ji=ct.litElementPolyfillSupport;Ji?.({LitElement:L});(ct.litElementVersions??=[]).push("4.2.2");var we=s=>Math.max(0,Math.min(75,s)),se=s=>`is-${s.angle===void 0?"unknown":s.feedback??"measured"}`,si=s=>s.angle===void 0?"?":s.readout??`${Math.round(s.angle)}\xB0`;function ni(s){let o=s.middle?122:150,e=s.middle?178:150,t=we(s.middle?.angle??0)/75*28;return{upperTransform:`rotate(${we(s.upper.angle??0)} ${o} 70)`,lowerTransform:`rotate(${-we(s.lower.angle??0)} ${e} 70)`,upperWidth:o-42,lowerX:e,lowerWidth:258-e,middlePath:`M 125 58 C 137 ${58-t} 163 ${58-t} 175 58 L 175 76 C 163 ${76-t} 137 ${76-t} 125 76 Z`}}function dt(s,o="theme"){let e=ni(s),t=e.upperTransform,i=e.lowerTransform,n=(r,a)=>s.stackLabels&&a.label?N`<text x=${r} y="124" text-anchor="middle" class="bed-graphic-label"><tspan
        x=${r}>${a.label}</tspan><tspan x=${r} dy="14">${si(a)}</tspan></text>`:N`<text x=${r} y="128" text-anchor="middle" class="bed-graphic-label">${`${a.label?`${a.label} `:""}${si(a)}`}</text>`;return N`
    <svg
      class="bed-graphic bed-graphic-${o} ${s.moving?"is-moving":""}"
      viewBox=${s.stackLabels?"0 -44 300 190":"0 -44 300 180"}
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
        <g class="bed-panel ${se(s.lower)}" transform=${i}>
          <rect class="bed-surface" x=${e.lowerX} y="58" width=${e.lowerWidth} height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel ${se(s.upper)}" transform=${t}>
          <rect class="bed-surface" x="42" y="58" width=${e.upperWidth} height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
        ${s.middle?N`<g class="bed-panel bed-lumbar-panel ${se(s.middle)}">
          <path class="bed-surface" d=${e.middlePath} />
        </g>`:""}
      </g>

      ${s.showLabels!==!1?N`
      ${n(s.middle?80:86,s.upper)}
      ${s.middle?n(150,s.middle):""}
      ${n(s.middle?220:214,s.lower)}
      `:""}
    </svg>
  `}function pt(s){let o=(e,t)=>{let i=ni(t);return N`
    <g
      class="dual-bed-side dual-bed-side-${e} ${t.moving?"is-moving":""}"
      fill=${`url(#abDual${e==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel ${se(t.lower)}"
        transform=${i.lowerTransform}
      >
        <rect class="dual-bed-surface" x=${i.lowerX} y="58" width=${i.lowerWidth} height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel ${se(t.upper)}"
        transform=${i.upperTransform}
      >
        <rect class="dual-bed-surface" x="42" y="58" width=${i.upperWidth} height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
      ${t.middle?N`<g class="dual-bed-panel bed-lumbar-panel ${se(t.middle)}">
        <path class="dual-bed-surface" d=${i.middlePath} />
      </g>`:""}
    </g>
  `};return N`
    <svg
      class="bed-graphic dual-bed-graphic ${s.left.moving||s.right.moving?"is-moving":""}"
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
      ${o("right",s.right)}
      ${o("left",s.left)}
    </svg>
  `}var ri=s=>typeof s=="number"&&Number.isFinite(s)?s:void 0;function $e(s,o){let e=o.estimate,t=e?s?.states[e]:void 0;if(!e||!t)return;let i=t.attributes,n=typeof i.bed_side=="string"?i.bed_side:void 0;if(t.state==="unavailable")return{motor:o.key,entityId:e,state:"not_calibrated",side:n};let r=i.estimate_state,a=r==="tracking"||r==="unconfirmed"||r==="unknown"?r:"unknown",l=Number.parseFloat(t.state);return{motor:o.key,entityId:e,state:a,percent:a==="tracking"&&Number.isFinite(l)?l:ri(i.last_estimate),reason:typeof i.estimate_reason=="string"?i.estimate_reason:void 0,maxAngle:ri(i.max_angle),side:n}}function ne(s,o){return o.flatMap(e=>{let t=$e(s,e);return t?[t]:[]})}function I(s,o){let e=s.percent===void 0?void 0:`${Math.round(s.percent)}`;return s.state==="tracking"&&e!==void 0?o("estimate.readout",{percent:e}):s.state==="unconfirmed"&&e!==void 0?o("estimate.readout_was",{percent:e}):s.state==="not_calibrated"?o("estimate.not_calibrated"):o("estimate.unknown")}function ht(s){if(s.length!==0)return s.some(o=>o.state==="unknown"||o.state==="not_calibrated")?"unknown":s.some(o=>o.state==="unconfirmed")?"unconfirmed":"estimated"}function ai(s){if(s.some(t=>t.state==="not_calibrated"))return{kind:"calibrate"};let o=s.filter(t=>t.state==="unknown");if(o.length)return{kind:"unknown",reason:o[0].reason};let e=s.filter(t=>t.state==="unconfirmed");if(e.length)return{kind:"unconfirmed",estimates:e}}function li(s,o){let e=o?s?.states[o]?.attributes.positions:void 0;return Array.isArray(e)?e.flatMap(t=>{if(!t||typeof t!="object")return[];let{id:i,name:n,button:r,beds:a}=t;return typeof i!="string"||typeof n!="string"||!a||typeof a!="object"?[]:[{id:i,name:n,button:r!==!1,beds:a}]}):[]}function ci(s,o){return s.filter(e=>{let t=Object.keys(e.beds);return t.length>0&&t.every(i=>o.includes(i))})}function di(s){let o=Object.keys(s.beds);return o.includes("left")&&o.includes("right")?"both":o.includes("left")?"left":o.includes("right")?"right":"bed"}function pi(s,o){let e=Object.entries(s.beds);return e.length>0&&e.every(([t,i])=>{let n=o[t]??[],r=Object.keys(i);return r.length>0&&r.every(a=>n.find(l=>l.motor===a)?.state==="tracking")})}function Ne(s){return s.length>0&&s.every(o=>o.state==="tracking")}function hi(s){if(!(!s||s.state!=="tracking")&&!(s.percent===void 0||s.maxAngle===void 0))return s.percent/100*s.maxAngle}function xe(s){let o=s.find(i=>i.key==="back"||i.key==="head"),e=s.find(i=>i.key==="legs"||i.key==="feet"),t=s.find(i=>i.key==="lumbar");return o&&e?{upper:o,lower:e,...t?{middle:t}:{}}:void 0}function ui(s,o,e=!1){let t=s.motors.filter(n=>{let r=n.angle??n.position,a=o.states[r??""]?.attributes.unit_of_measurement;return a==="\xB0"||e&&a==="%"}),i=s.motors.filter(n=>{let r=o.states[n.estimate??""];return r!==void 0&&(e||typeof r.attributes.max_angle=="number")});return xe(t)!==void 0||xe(i)!==void 0}function Fe(s,o=!1){if(!o)return s;let e=xe(s);if(!e?.middle)return s;let t=[e.upper,e.middle,e.lower];return[...t,...s.filter(i=>!t.includes(i))]}function mi(s){let o=Math.max(0,Math.min(100,s));return{angle:o*.75,readout:`${Math.round(o)}%`}}function gi(s,o,e=!1){let t=s.angle??s.position,i=o.states[t??""],n=i?.attributes.unit_of_measurement;if(n!=="\xB0"&&n!=="%"||n==="%"&&!e)return;let r=i.state.trim();if(r==="")return;let a=Number(r);if(Number.isFinite(a))return n==="\xB0"?{angle:a}:mi(a)}function ut(s,o,e){if(!s)return;if(!o){let n=hi(s);return n===void 0?void 0:{angle:n,readout:`\u2248 ${Math.round(we(n))}\xB0`,feedback:"estimated"}}let{percent:t,state:i}=s;return t===void 0||i!=="tracking"&&i!=="unconfirmed"?{feedback:"unknown"}:{...mi(t),readout:I(s,e),feedback:i==="tracking"?"estimated":"unconfirmed"}}var Ge=s=>!!(s.cover||s.up||s.down),mt=s=>s.motors.filter(o=>o.position&&!Ge(o)),gt=s=>s.motors.some(Ge)||mt(s).length>0||!!s.synchro||!!s.controlSide||!!s.stop||!!s.extraStops?.length||!!s.motorExtras?.length,ft=s=>pe(s.lights)||!!s.lights.state,_t=s=>s.presets.length+s.presetSaves.length>0,vt=({massage:s})=>s.buttons.length>0||s.numbers.length>0||!!s.selects?.length||!!s.switches?.length||!!s.states?.length||!!s.timer,bt=s=>s.utility.length>0||!!s.utilitySwitches?.length||!!s.utilityNumbers?.length||!!s.utilitySelects?.length||!!s.utilityStates?.length,yt=({climate:s})=>[...s.entities,...s.selects,...s.numbers];function ke(s,o,e){return{graphic:ui(s,o,e?.show_percentage_graphic===!0),motors:gt(s),firmness:s.firmness.length>0,presets:_t(s),saved_positions:!!s.savedPositions,memory:s.memory.length>0,lighting:ft(s),massage:vt(s),utility:bt(s),climate:yt(s).length>0,connection:!!(s.connect||s.disconnect)}}var Qi={attribute:!0,type:String,converter:ge,reflect:!1,hasChanged:je},eo=(s=Qi,o,e)=>{let{kind:t,metadata:i}=e,n=globalThis.litPropertyMetadata.get(i);if(n===void 0&&globalThis.litPropertyMetadata.set(i,n=new Map),t==="setter"&&((s=Object.create(s)).wrapped=!0),n.set(e.name,s),t==="accessor"){let{name:r}=e;return{set(a){let l=o.get.call(this);o.set.call(this,a),this.requestUpdate(r,l,s,!0,a)},init(a){return a!==void 0&&this.C(r,void 0,s,a),a}}}if(t==="setter"){let{name:r}=e;return function(a){let l=this[r];o.call(this,a),this.requestUpdate(r,l,s,!0,a)}}throw Error("Unsupported decorator location: "+t)};function re(s){return(o,e)=>typeof e=="object"?eo(s,o,e):((t,i,n)=>{let r=i.hasOwnProperty(n);return i.constructor.createProperty(n,t),r?Object.getOwnPropertyDescriptor(i,n):void 0})(s,o,e)}function R(s){return re({...s,state:!0,attribute:!1})}var _i=["glance","quick","controls"],vi=Object.fromEntries(j.map(s=>[`show_${s}`,!0])),bi={name:"",show_header:!0,animate:!0,show_graphic_labels:!0,show_percentage_graphic:!1,show_lumbar_graphic:!1,...vi,section_order:[],memory_save:!0,memory_slots:[],tap_to_move:!1};function Ie(s){return{...s,show_header:!0,...vi,...s.dialog_config,type:s.type,device_id:s.device_id,layout:"full",open_dialog:!1,navigation_path:void 0,dialog_config:void 0}}function yi(s,o){let e={...s,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:o==="glance"?"names":"angles",show_side_selector:!0,show_motors:o==="controls",show_lighting:!1,show_connection:!1,animate:!0};return o==="glance"?e.compact_actions=[]:delete e.compact_actions,e}function wi(s,o){return[...o.presets,...o.memory.flatMap(e=>e.goto?[e.goto]:[])].flatMap(e=>{let t=s.entities[e]?.translation_key;return t?[{key:t,entityId:e}]:[]})}function fi(s,o){let e=s.entities[o],t=s.states[o]?.attributes.bed_side;return Object.values(s.entities).some(i=>i.entity_id!==o&&i.device_id===e?.device_id&&i.translation_key===e?.translation_key&&s.states[i.entity_id]?.attributes.bed_side===t)}function $i(s,o,e){if(!e.includes(".")){let l=[...o].reverse();return l.find(p=>p.key===e)??l.find(p=>p.key.replace(/_(left|right|both)$/,"")===e)}let t=o.find(l=>l.entityId===e);if(t)return t;let i=s.entities[e]?.translation_key,n=o.filter(l=>l.key===i),r=S(s,e),a=n.find(l=>S(s,l.entityId)===r);return a||(n.length===1&&!fi(s,e)&&!fi(s,n[0].entityId)?n[0]:void 0)}function ae(s,o,e){let t=wi(s,o);if(e){let r=e.flatMap(a=>{let l=$i(s,t,a);return l?[l]:[]});return r.filter((a,l)=>r.findIndex(p=>p.entityId===a.entityId)===l)}let i=t.find(r=>r.key==="preset_flat"),n=t.find(r=>r.key.startsWith("preset_memory_"))??t.find(r=>r!==i);return[i,n].filter(r=>r!==void 0)}function wt(s,o,e,t){let i=[],n=l=>i.find(({action:p,sideOptions:u})=>$i(s,u,l)?.entityId===p.entityId),r=e?[e,...o.filter(l=>l!==e)]:o;for(let l of r){let p=wi(s,l.bed);for(let u of p)n(u.entityId)||i.push({action:u,sideOptions:p})}let a=(t??(e?ae(s,e.bed).map(l=>l.entityId):[])).flatMap(l=>{let p=n(l);return p?[p.action.entityId]:[]});return{options:i.map(({action:l})=>l),selected:[...new Set(a)]}}function Ue(s){return s.stop?[s.stop]:s.motors.flatMap(o=>o.cover?[o.cover]:[])}function Ve(s){if(!(!s||!s.startsWith("/")||/^\/[/\\]/.test(s)||/[\\\s]/.test(s)))return s}function U(s,o){let e=Re(s,o),t=de(s,e);if(e&&t.length){let i=t.map(r=>({key:r,label:D(s,r)??r,bed:B(s,r)})),n=B(s,e);return te(n,i.map(r=>r.bed)),[{key:"both",label:f(s,"card.both_sides"),bed:n},...i]}if(Pe(s,o)){let i=["both","left","right"].map(n=>({key:n,label:f(s,`card.${n==="both"?"both_sides":`${n}_side`}`),bed:B(s,o,n)}));return te(i[0].bed,[i[1].bed,i[2].bed]),i}return[{key:"both",label:f(s,"card.both_sides"),bed:B(s,o)}]}var xi="5.0.0b8";var to="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",io="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",oo=(s,o)=>s.length===o.length&&s.every((e,t)=>e===o[t]),J=class extends L{constructor(){super(...arguments);this._editingDialog=!1;this._computeLabel=e=>f(this.hass,`editor.${e.name}`)}get _config(){return this._editingDialog&&this._rootConfig?Ie(this._rootConfig):this._rootConfig}setConfig(e){this._rootConfig=e,(e.layout!=="compact"||!e.open_dialog)&&(this._editingDialog=!1)}_bed(){let e=this._config?.device_id;if(!this.hass||!e)return;let t=U(this.hass,e).map(r=>r.bed),i=t[0];if(!i)return;let n=new Map;for(let r of t)for(let a of r.memory){let l=n.get(a.slot);n.set(a.slot,{slot:a.slot,goto:l?.goto??a.goto,save:l?.save??a.save})}return{...i,memory:[...n.values()].sort((r,a)=>r.slot-a.slot)}}_presentKeys(e){let t=this.hass?U(this.hass,this._config?.device_id).map(i=>i.bed):[e];return j.filter(i=>t.some(n=>ke(n,this.hass,this._config)[i]))}_orderedKeys(e){let t=this._presentKeys(e),n=(this._config?.section_order??[]).filter(a=>t.includes(a)),r=t.filter(a=>!n.includes(a));return[...n,...r]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=f(this.hass,"card.memory_slot",{slot:String(e.slot)});return t?S(this.hass,t,i):i}_savedActionIds(e){let t=e.compact_actions;if(!this.hass||!Array.isArray(t)||t.every(l=>typeof l!="string"||l.includes(".")))return t;let i=U(this.hass,e.device_id),n=i.find(l=>l.key===(e.default_target??"both"));if(!t.every(l=>typeof l=="string"))return t;let r=wt(this.hass,i,n,t).selected;if(r.length!==new Set(t).size)return t;let a=l=>ae(this.hass,l.bed,t).map(p=>p.entityId).join()===ae(this.hass,l.bed,r).map(p=>p.entityId).join();return i.every(a)?r:t}_emit(e){if(e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this._editingDialog||(e.compact_actions=this._savedActionIds(e)),e.compact_actions===void 0&&delete e.compact_actions,this._editingDialog&&this._rootConfig){let t=Object.fromEntries(Object.entries(bi).map(([i,n])=>[i,e[i]??n]));e={...this._rootConfig,dialog_config:{...this._rootConfig.dialog_config,...t}}}this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return this._editingDialog?[{name:"name",selector:{text:{}}}]:[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;this._editingDialog||(i.device_id!==t.device_id&&delete i.default_target,i.device_id=t.device_id||void 0),t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let n=this._orderedKeys(e),r=n.indexOf(t),a=r+i;if(r<0||a<0||a>=n.length)return;[n[r],n[a]]=[n[a],n[r]];let l=this._cfg;oo(n,this._presentKeys(e))?delete l.section_order:l.section_order=n,this._emit(l)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let n=this._memorySlots(e),r=this._config?.memory_slots,a=r&&r.length?r.map(Number):[...n];i?a.includes(t)||a.push(t):a=a.filter(p=>p!==t),a.sort((p,u)=>p-u);let l=this._cfg;a.length===n.length?delete l.memory_slots:l.memory_slots=a,this._emit(l)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?d`
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.sections")}</div>
        ${t.map((i,n)=>{let r=this._config?.[`show_${i}`]!==!1;return d`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${n===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${f(this.hass,"editor.move_up")}
                  aria-label=${f(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${to}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${n===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${f(this.hass,"editor.move_down")}
                  aria-label=${f(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${io}></path></svg>
                </button>
              </div>
              <ha-switch
                .checked=${r}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              >${f(this.hass,`editor.show_${i}`)}</ha-switch>
            </div>
          `})}
      </div>
    `:c}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return c;let i=e.memory.some(r=>r.save),n=e.memory.length>1;return!i&&!n?c:d`
      <div class="group">
        <div class="group-title">
          ${f(this.hass,"editor.memory_group")}
        </div>
        ${i?d`<div class="row">
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                >${f(this.hass,"editor.memory_save")}</ha-switch>
              </div>`:c}
        ${n?d`<div class="sub">
                <div class="sub-label">
                  ${f(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(r=>d`
                    <div class="row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${a=>this._toggleSlot(e,r.slot,a.target.checked)}
                      >${this._slotLabel(r)}</ha-checkbox>
                    </div>
                  `)}
              </div>`:c}
      </div>
    `}_tapToMoveToggle(){return d`<div class="row">
        <ha-switch .checked=${this._config?.tap_to_move===!0}
          @change=${e=>this._setOption("tap_to_move",e.target.checked||void 0)}
        >${f(this.hass,"editor.tap_to_move")}</ha-switch>
      </div>
      <p class="hint">${f(this.hass,"editor.tap_to_move_hint")}</p>`}_motorsGroup(e){return this._config?.show_motors===!1||!this._presentKeys(e).includes("motors")?c:d`<div class="group">
      <div class="group-title">${f(this.hass,"editor.motors_group")}</div>
      ${this._tapToMoveToggle()}
    </div>`}_setOption(e,t){this._emit({...this._cfg,[e]:t})}_compactToggle(e,t){return d`<div class="row">
      <ha-switch .checked=${this._config?.[e]??t}
        @change=${i=>this._setOption(e,i.target.checked)}
      >${f(this.hass,e==="show_connection"?"editor.compact_connection":`editor.${e}`)}</ha-switch>
    </div>`}_compactGroup(){let e=this._config,t=U(this.hass,e.device_id),i=t.find(l=>l.key===(e.default_target??"both")),{options:n,selected:r}=wt(this.hass,t,i,e.compact_actions),a=[...r,...n.map(l=>l.entityId).filter(l=>!r.includes(l))];return d`
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        ${this._graphicOptions()}
        <label class="row"><span class="label">${f(this.hass,"editor.compact_labels")}</span>
          <select .value=${e.compact_labels??"angles"}
            @change=${l=>this._setOption("compact_labels",l.target.value)}>
            ${["angles","names","none"].map(l=>d`
              <option value=${l}>${f(this.hass,`editor.labels_${l}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        ${this._compactToggle("open_dialog",!1)}
        ${e.open_dialog?d`<div class="recipes">
          <button @click=${()=>{this._editingDialog=!0}}>
            ${f(this.hass,"editor.configure_dialog")}
          </button>
        </div>`:c}
        <label class="row path-row"><span class="label">${f(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${e.navigation_path??""} placeholder="/dashboard/bed"
            @change=${l=>this._setOption("navigation_path",l.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.compact_controls")}</div>
        ${t.length>1||!i?d`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${f(this.hass,"editor.default_target")}</span>
            <select .value=${e.default_target??"both"}
              @change=${l=>this._setOption("default_target",l.target.value)}>
              ${i?c:d`<option value=${e.default_target}>${f(this.hass,"compact.target_missing")}</option>`}
              ${t.map(l=>d`<option value=${l.key}>${l.label}</option>`)}
            </select>
          </label>`:c}
        ${this._compactToggle("show_motors",!1)}
        ${e.show_motors===!0?this._tapToMoveToggle():c}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${f(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${f(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${f(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${f(this.hass,"editor.labels_none")}</button>
        </div>
        ${a.map(l=>{let p=n.find(y=>y.entityId===l),u=r.includes(l),h=r.indexOf(l),g=y=>{let b=[...r];[b[h],b[h+y]]=[b[h+y],b[h]],this._setOption("compact_actions",b)};return d`<div class="row">
            <ha-checkbox .checked=${u} @change=${y=>this._setOption("compact_actions",y.target.checked?[...r,l]:r.filter(b=>b!==l))}
            >${S(this.hass,p.entityId)}</ha-checkbox>
            <button class="icon-btn" ?disabled=${!u||h===0}
              aria-label=${f(this.hass,"editor.move_up")} @click=${()=>g(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!u||h===r.length-1}
              aria-label=${f(this.hass,"editor.move_down")} @click=${()=>g(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return d`<div class="group">
      <label class="row"><span class="label">${f(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${e=>this._setOption("layout",e.target.value)}>
          <option value="full">${f(this.hass,"editor.layout_full")}</option>
          <option value="compact">${f(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${f(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${_i.map(e=>d`
        <button @click=${()=>this._emit({...yi(this._config,e)})}>
          ${f(this.hass,`editor.recipe_${e}`)}
        </button>`)}</div>
    </div>`}_graphicOptions(){let e=this._config;if(!this.hass||e.show_graphic===!1)return c;let t=U(this.hass,e.device_id),i=t.map(p=>p.bed),n=t.length>1?t.filter(p=>p.key!=="both"):t,r=p=>ke(p.bed,this.hass,{...e,show_percentage_graphic:!0}).graphic;if(!(e.layout==="compact"?n.every(r):t.some(r)))return c;let l=i.some(p=>p.motors.some(u=>u.key==="lumbar"));return d`
      ${this._compactToggle("show_graphic_labels",!0)}
      ${this._compactToggle("show_percentage_graphic",!1)}
      ${l||e.show_lumbar_graphic?this._compactToggle("show_lumbar_graphic",!1):c}
    `}_graphicGroup(){let e=this._graphicOptions();return e===c?c:d`<div class="group">
      <div class="group-title">${f(this.hass,"editor.graphic_group")}</div>
      ${e}
    </div>`}render(){if(!this.hass||!this._config)return c;let e=this._bed();return d`
      ${this._editingDialog?d`<div class="group">
        <div class="group-title">${f(this.hass,"editor.dialog_configuration")}</div>
        <p class="hint">${f(this.hass,"editor.dialog_configuration_hint")}</p>
        <div class="recipes"><button @click=${()=>{this._editingDialog=!1}}>
          ${f(this.hass,"editor.back_to_compact")}
        </button></div>
      </div>`:c}
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._editingDialog?c:this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():d`
        ${this._graphicGroup()}
        ${e?this._motorsGroup(e):c}
        ${e?this._sectionsGroup(e):c}
        ${e?this._memoryGroup(e):c}
      `}
    `}};J.styles=ue`
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
    .label,
    .row > ha-switch,
    .row > ha-checkbox {
      flex: 1;
      min-width: 0;
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
  `,C([re({attribute:!1})],J.prototype,"hass",2),C([R()],J.prototype,"_rootConfig",2),C([R()],J.prototype,"_editingDialog",2);He("adjustable-bed-card-editor",J);var so=new Set(["back","legs","head","feet"]),P=class extends L{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._tapRevision=0;this._detailsOpen=!1;this._watched=[];this._awaitingState=[];this._compactStopTargets=new Map;this._hold=new Ce({pulse:(e,t)=>qe(this.hass,e,t),lease:(e,t,i)=>Tt(this.hass,e,t,i),stopCover:(e,t)=>this._stopCompactTarget(e,t??e),stopBed:e=>{e&&this._stopCompactTarget(e)},changed:()=>{this._tapRevision++}});this._focusLossCleanup=null;this._windowPointerEnd=e=>{this._hold.endActiveFromPointer(e.pointerId,e.type==="pointercancel"||e.button===0)};this._windowKeyUp=e=>{(e.key==="Enter"||e.key===" ")&&this._hold.endKeyboard(void 0,void 0,e.key)};this._navigate=()=>{let e=Ve(this._config?.navigation_path);e&&(this._hold.abandon(),history.pushState(null,"",e),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))};this._openDetails=async()=>{if(!this._config?.open_dialog){this._navigate();return}this._hold.abandon(),this._detailsCard||(this._detailsCard=document.createElement(this.localName),this._detailsCard.setConfig(Ie({...this._config,default_target:this._activePairedPane}))),this._detailsCard.hass=this.hass,this._detailsOpen=!0,await this.updateComplete;let e=this.renderRoot.querySelector(".bed-details-dialog");e&&!e.open&&e.showModal()};this._closeDetails=()=>{if(!this._detailsOpen&&!this._detailsCard)return;let e=this.renderRoot.querySelector(".bed-details-dialog");e?.open&&e.close(),this._detailsOpen=!1,this._detailsCard=void 0};this._detailsBackdrop=e=>{if(e.target!==e.currentTarget)return;let t=e.currentTarget.getBoundingClientRect();(e.clientX<t.left||e.clientX>t.right||e.clientY<t.top||e.clientY>t.bottom)&&this._closeDetails()};this._openSettings=()=>{this._hold.abandon(),history.pushState(null,"","/config/integrations/integration/adjustable_bed"),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}}))};this._closeEstimateDialog=()=>{let e=this.renderRoot?.querySelector?.("dialog.estimate-dialog");e?.open&&e.close();let t=this._estimateDialog;t?.kind==="reference"&&t.phase==="lowering"&&this._stopEstimate(t.ctx),this._estimateDialog=void 0}}connectedCallback(){super.connectedCallback(),this._removeHoldLifecycle=Rt(this._hold,document,window),window.addEventListener("pointerup",this._windowPointerEnd),window.addEventListener("pointercancel",this._windowPointerEnd),window.addEventListener("keyup",this._windowKeyUp),this._focusLossCleanup=At(window,document,()=>document.visibilityState==="hidden",()=>this._hold.releaseOnFocusLoss())}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===O)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._detailsOpen&&this._closeDetails(),this._config&&(this._compactStopTargets.size>0?this._stopCompact():this._hold.abandon()),(e.device_id!==this._config?.device_id||e.default_target!==this._config?.default_target)&&(this._activePairedPane=e.default_target??"both"),this._config=e}getCardSize(){if(this._config?.layout!=="compact")return this._fullCardSize();let e=this._config;return Math.ceil((24+(e.show_header!==!1?36:0)+(e.show_graphic!==!1?150:0)+(e.compact_labels!=="none"?40:0)+(e.compact_actions?.length===0?0:110)+(e.show_motors===!0?180:0)+(e.show_lighting===!0?70:0)+(e.show_connection===!0?50:0))/50)}_fullCardSize(){let e=this._config,t=this.hass;if(!e||!t)return 8;let i=U(t,e.device_id).map(r=>r.bed),n=r=>j.filter(a=>e[`show_${a}`]!==!1&&ke(r,t,e)[a]).reduce((a,l)=>a+(l==="graphic"?3:l==="motors"?1+r.motors.length:2),0);return(i.length>1?2:1)+Math.max(0,...i.map(n))}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){window.removeEventListener("pointerup",this._windowPointerEnd),window.removeEventListener("pointercancel",this._windowPointerEnd),window.removeEventListener("keyup",this._windowKeyUp),this._focusLossCleanup?.(),this._focusLossCleanup=null,this._removeHoldLifecycle?.(),this._removeHoldLifecycle=void 0,super.disconnectedCallback(),this._hold.abandon(),this._closeEstimateDialog(),this._closeDetails()}shouldUpdate(e){if(e.has("_config")||e.has("_detailsOpen")||e.has("_saveModeFor")||e.has("_activePairedPane")||e.has("_synchronizingTo")||e.has("_synchronizationFailed")||e.has("_estimateDialog")||e.has("_savedEditFor")||e.has("_tapRevision")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices||t.formatEntityName!==this.hass.formatEntityName)return!0;for(let i of[...this._watched,...this._awaitingState])if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return c;if(!this._config.device_id)return this._notice("card.no_device");let e=this.hass.devices??{};if(Object.keys(e).length>0&&!e[this._config.device_id])return this._notice("card.device_missing");let t=this.hass.states;this._awaitingState=Object.values(this.hass.entities).filter(p=>p.platform===O&&!t[p.entity_id]).map(p=>p.entity_id);let i=Re(this.hass,this._config.device_id),n=de(this.hass,i);if(i&&n.length)return this._renderPaired(i,n);if(this._config.device_id&&Pe(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let r=B(this.hass,this._config.device_id);if(this._watched=this._collectWatched(r),G(r))return this._notice("card.no_entities");if(this._config.layout==="compact")return this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:r}],!1);let a=this._config.device_id,l={deviceId:a,paired:!1,sides:[{key:"bed",deviceId:a,label:this._title(),motors:r.motors}],savedPositions:r.savedPositions};return d`
      <ha-card>
        ${this._header(r)}
        ${this._renderSections(r,"theme",void 0,void 0,void 0,l)}
        ${this._estimateDialogTemplate()}
      </ha-card>
    `}_renderSections(e,t="theme",i,n,r,a){let l=this._config,p={graphic:()=>l.show_graphic!==!1?i??this._graphic(e,t):c,motors:()=>l.show_motors!==!1?this._motors(e,n,r,a):c,firmness:()=>l.show_firmness!==!1?this._firmness(e):c,presets:()=>l.show_presets!==!1?this._presets(e):c,saved_positions:()=>l.show_saved_positions!==!1&&a?this._savedPositions(a):c,memory:()=>l.show_memory!==!1?this._memory(e):c,lighting:()=>l.show_lighting!==!1?this._lighting(e):c,massage:()=>l.show_massage!==!1?this._massage(e):c,utility:()=>l.show_utility!==!1?this._utility(e):c,climate:()=>l.show_climate!==!1?this._climate(e):c,connection:()=>l.show_connection!==!1?this._connection(e):c};return this._orderedSections().map(u=>p[u]?.()??c)}_renderPaired(e,t){let i=this.hass,n=B(i,e),r=t.map((g,y)=>({key:g,label:D(i,g)??g,shortLabel:Bt(D(i,g)??g,D(i,e)),bed:B(i,g),graphicTone:y===0?"left":"right",synchronizationTarget:{deviceId:g}}));te(n,r.map(g=>g.bed));let a=r.flatMap(g=>g.bed.stop?[g.bed.stop]:[]),l=n.stop,p=[...new Set([...l?[l]:[],...a])],u=r.map((g,y)=>({key:this._estimateSideKey(g.bed,y),deviceId:g.key,label:g.label,motors:g.bed.motors})),h=[{key:"both",label:f(i,"card.both_sides"),bed:n,stopScope:p,remainingStopIds:a,estimate:{deviceId:e,side:"both",paired:!0,sides:u,savedPositions:n.savedPositions}},...r.map((g,y)=>({...g,stopScope:g.bed.stop?[g.bed.stop]:[],estimate:{deviceId:g.key,paired:!0,sides:[u[y]],savedPositions:n.savedPositions}}))];return this._watched=[n,...r.map(g=>g.bed)].flatMap(g=>this._collectWatched(g)),G(n)&&r.every(g=>G(g.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,h)}_renderSingleAddressPaired(e){let t=this.hass,i={both:B(t,e,"both"),left:B(t,e,"left"),right:B(t,e,"right")};te(i.both,[i.left,i.right]);let n=[i.left.stop,i.right.stop].filter(r=>r!==void 0);return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>G(r))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:f(t,"card.both_sides"),bed:i.both,stopScope:[...new Set([i.both.stop,...n].filter(r=>r!==void 0))],remainingStopIds:n},{key:"left",label:f(t,"card.left_side"),bed:i.left,graphicTone:"left",stopScope:i.left.stop?[i.left.stop]:[],synchronizationTarget:{deviceId:e,side:"left"}},{key:"right",label:f(t,"card.right_side"),bed:i.right,graphicTone:"right",stopScope:i.right.stop?[i.right.stop]:[],synchronizationTarget:{deviceId:e,side:"right"}}])}_renderPairedCard(e,t){if(this._config?.layout==="compact")return this._renderCompact(e,t,!0);let i=t.filter(l=>!G(l.bed)),n=i.find(l=>l.key===this._activePairedPane)??i[0],r=i.filter(l=>l.key!=="both"),a=n.key==="both";return d`
      <ha-card class="paired-card">
        ${this._header(n.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
          @keydown=${l=>this._paneTabKey(l,i,n.key)}
        >
          ${i.map((l,p)=>d`
              <button
                class="pane-tab side-${l.graphicTone??"theme"} ${l.key===n.key?"active":""}"
                role="tab"
                id=${`pane-tab-${p}`}
                aria-controls="pane-panel"
                aria-selected=${l.key===n.key?"true":"false"}
                aria-label=${l.label}
                tabindex=${l.key===n.key?"0":"-1"}
                @click=${()=>this._selectPairedPane(l.key)}
              >
                ${l.graphicTone?d`<span class="dual-swatch" aria-hidden="true"></span>`:c}
                <span>${this._paneTabLabel(l)}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" id="pane-panel"
          aria-labelledby=${`pane-tab-${i.indexOf(n)}`}>
          ${this._renderSections(n.bed,n.graphicTone,a?this._pairedOverview(r):void 0,n.stopScope,n.remainingStopIds,n.estimate)}
          ${a&&this._config?.show_lighting!==!1?this._combinedLighting(n.bed,r):c}
          ${a&&this._config?.show_connection!==!1?this._combinedBluetooth(r):c}
        </div>
        ${this._estimateDialogTemplate()}
      </ha-card>
    `}_paneTabLabel(e){return e.key==="both"?f(this.hass,"card.both"):e.shortLabel??e.label}_paneTabKey(e,t,i){let n=t.findIndex(p=>p.key===i),r=getComputedStyle(this).direction==="rtl",a={ArrowRight:r?-1:1,ArrowLeft:r?1:-1}[e.key],l=a!==void 0?(n+a+t.length)%t.length:e.key==="Home"?0:e.key==="End"?t.length-1:void 0;l!==void 0&&(e.preventDefault(),this._selectPairedPane(t[l].key),this.updateComplete.then(()=>this.renderRoot.querySelector(`#pane-tab-${l}`)?.focus()))}_renderCompact(e,t,i){let n=this._config,r=t.find(v=>v.key===this._activePairedPane),a=r?.bed,l=a?ae(this.hass,a,n.compact_actions):[],p=n.show_motors===!0&&a?a.motors.filter(v=>v.cover||v.up||v.down||v.position):[],u=l.length>0||p.length>0||n.show_lighting===!0,h=n.compact_actions?.length!==0||n.show_motors===!0||n.show_lighting===!0,g=i?t.filter(v=>v.key!=="both"):t,y=!!a&&Ue(a).length>0,b=l.length>0||p.length>0,E=n.open_dialog||Ve(n.navigation_path);return d`
      <ha-card class="compact-card ${h?"":"compact-glance"} ${n.animate===!1?"no-animation":""}">
        ${n.show_header!==!1?d`
          <div class="compact-header">
            <span class="title">${this._title(e)}</span>
            ${E?d`<button class="compact-open" @click=${this._openDetails}
              aria-label=${f(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:c}
          </div>`:c}
        ${i&&h?n.show_side_selector!==!1?d`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${t.filter(v=>!G(v.bed)).length}`}
            aria-label=${f(this.hass,"compact.target")}>
            ${t.filter(v=>!G(v.bed)).map(v=>d`
              <button class="pane-tab side-${v.graphicTone??"theme"} ${v.key===r?.key?"active":""}"
                aria-pressed=${v.key===r?.key?"true":"false"}
                aria-label=${v.label}
                title=${v.label}
                @click=${()=>this._selectPairedPane(v.key)}>
                ${v.graphicTone?d`<span class="dual-swatch" aria-hidden="true"></span>`:c}
                <span class="compact-tab-label">${this._paneTabLabel(v)}</span>
              </button>`)}
          </div>`:d`<div class="compact-target">
            ${r?f(this.hass,"compact.target_fixed",{side:r.label}):f(this.hass,"compact.target_missing")}
          </div>`:c}
        ${n.show_graphic!==!1?this._compactGraphic(g):c}
        ${this._compactReadouts(g)}
        ${!r&&h?d`<div class="hint" role="status">
          ${f(this.hass,"compact.target_missing")}</div>`:c}
        ${p.length?d`<div class="rows compact-motors">
          ${p.map(v=>v.cover||v.up||v.down?this._motorRow(v,a?.stop,!0,r?.stopScope,r?.remainingStopIds):this._moreInfoRow(v.position))}
        </div>`:c}
        ${l.length||b||this._compactStopTargets.size?d`
          <div class="tiles compact-actions">
            ${l.map(({entityId:v})=>d`<button class="tile"
              ?disabled=${!y||!this._available(v)}
              @click=${()=>this._compactRecall(v,a)}>
              ${this._icon(v)}<span class="tile-label">${S(this.hass,v)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!y&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(a)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${f(this.hass,"action.stop")}</span>
            </button>
          </div>`:c}
        ${n.show_lighting===!0&&a?d`
          ${this._lighting(a)}
          ${i&&r?.key==="both"?this._combinedLighting(a,g):c}
        `:c}
        ${n.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(g):d`<div class="compact-connections">
          ${g.map(v=>{let k=this._connectionStatus(v.bed);return k?d`<span>${this._connectionDot(v.bed)}
              ${v.label}: ${f(this.hass,`status.${k}`)}</span>`:c})}
        </div>`:c}
        ${!u&&n.show_graphic===!1&&n.compact_labels==="none"&&n.show_header===!1&&n.show_connection!==!0?d`<div class="hint">${this._title(e)}</div>`:c}
        ${this._estimateDialogTemplate()}
      </ha-card>
      ${this._detailsOpen?d`<dialog class="bed-details-dialog" aria-label=${this._title(e)}
        @close=${this._closeDetails} @click=${this._detailsBackdrop}>
        <div class="bed-details-heading">
          <strong>${this._title(e)}</strong>
          <button class="bed-details-close" @click=${this._closeDetails}
            aria-label=${f(this.hass,"action.close")}>✕</button>
        </div>
        <div class="bed-details-content">${this._detailsCard}</div>
      </dialog>`:c}`}_compactGraphic(e){let t=e.map(h=>this._graphicState(h.bed)),i=t[0],n=t[1],r=t.length>0&&t.every(h=>h!==void 0),a=e.map((h,g)=>`${h.label}: ${t[g]?this._positionSummary(t[g]):f(this.hass,"compact.no_position")}`).join(". "),l=r&&i?n?pt({left:i,right:n}):dt({...i,upper:{...i.upper,label:i.middle?i.upper.label:void 0},lower:{...i.lower,label:i.middle?i.lower.label:void 0}}):d`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${f(this.hass,"compact.no_position")}</span></div>`,p=this._config?.show_percentage_graphic===!0&&r&&t.some(h=>h?.estimated)?ht(e.flatMap(h=>ne(this.hass,h.bed.motors))):void 0,u=d`${l}${p?d`<span class="estimate-chip chip-${p}
      compact-estimate-chip">${this._t(`estimate.chip_${p}`)}</span>`:c}`;return this._config?.open_dialog||Ve(this._config?.navigation_path)?d`<button class="compact-graphic" @click=${this._openDetails}
          aria-label="${f(this.hass,"compact.open")}. ${a}">${u}</button>`:d`<div class="compact-graphic" role="img" aria-label=${a}>${u}</div>`}_compactReadouts(e){let t=this._config?.compact_labels??"angles";return t==="none"?c:d`<div class="compact-readouts ${t==="names"?"compact-names":""}">
      ${e.map(i=>d`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span class="compact-side-label" aria-hidden="true">${i.shortLabel??i.label}</span>
          <span class="visually-hidden">${i.label}</span>
        </span>
        ${t==="angles"?d`<span class="compact-position"
          title=${Fe(i.bed.motors,this._config?.show_lumbar_graphic===!0).map(n=>`${this._motorName(n)} ${this._compactReadout(n)??"?"}`).join(" \xB7 ")}
        >${Fe(i.bed.motors,this._config?.show_lumbar_graphic===!0).filter(n=>n.angle||n.position||n.cover||n.estimate).map(n=>this._compactReadout(n)??"?").join(" / ")||f(this.hass,"compact.no_position")}</span>`:c}
      </div>`)}
    </div>`}_compactReadout(e){return e.angle||e.position||!e.estimate?this._readout(e):ut($e(this.hass,e),!0,(t,i)=>this._t(t,i))?.readout??"?"}_available(e){let t=this._state(e)?.state;return t!==void 0&&t!=="unavailable"}_compactRecall(e,t){this._hold.abandon(),Ue(t).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(e),this.requestUpdate()}_stopCompact(e){let t=[...new Set([...e?Ue(e):[],...this._compactStopTargets.keys()])];this._hold.cancelForStopScope(t);for(let i of t)this._compactStopTargets.has(i)||this._compactStopTargets.set(i,Symbol());for(let i of this._compactStopTargets.keys())this._stopCompactTarget(i);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(e,t=e){let i=this._compactStopTargets.get(t),n=e.startsWith("cover.");this.hass?.callService(n?"cover":"button",n?"stop_cover":"press",{entity_id:e}).then(()=>{i!==void 0&&this._compactStopTargets.get(t)===i&&(this._compactStopTargets.delete(t),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(e){this._activePairedPane!==e&&(this._hold.endTap(),this._activePairedPane=e,this._saveModeFor=void 0,this._savedEditFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.attributes?.state_detail==="connecting"?"connecting":t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?d`<span
      class="connection-dot ${t}"
      title=${f(this.hass,`status.${t}`)}
    ></span>`:c}_pairedOverview(e){let t=e.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(t.length<2)return c;let[i,n]=t;return d`
      <div class="graphic dual-graphic">
        ${pt({left:i.graphic,right:n.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,n].map(({pane:r,graphic:a},l)=>d`
            <div class="dual-readout side-${l===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(a)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,n.pane)}
    `}_synchronizeSelector(e,t){if(!e.synchronizationTarget||!t.synchronizationTarget)return c;let i=this._synchronizationPlan(e.bed,t.bed),n=this._synchronizationPlan(t.bed,e.bed);if(i.length===0&&n.length===0)return c;let r=this._synchronizingTo!==void 0;return d`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${f(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${f(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"left")}
          >
            ${this._synchronizingTo==="left"?d`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:d`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${f(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||n.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"right")}
          >
            ${this._synchronizingTo==="right"?d`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:d`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?d`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${f(this.hass,"sync.incomplete")}</span>
          </div>`:c}
    `}_synchronizationPlan(e,t){let i=new Map(t.motors.map(a=>[a.key,a])),n=e.motors.filter(a=>so.has(a.key)&&i.has(a.key)&&this._hasPositionFeedback(a)&&this._hasPositionFeedback(i.get(a.key)));if(n.length===0)return[];let r=n.map(a=>({motor:a.key,position:this._angle(a)}));return r.some(a=>a.position===void 0)||n.some(a=>this._angle(i.get(a.key))===void 0)?[]:r}_hasPositionFeedback(e){return e.angle!==void 0||e.position!==void 0}async _synchronizePositions(e,t,i){if(this._synchronizingTo||!this.hass)return;let n=i==="left"?e:t,r=i==="left"?t:e,a=r.synchronizationTarget;if(!a)return;let l=this._synchronizationPlan(n.bed,r.bed);if(l.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(O,"set_positions",{device_id:[a.deviceId],positions:l,...a.side?{side:a.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,...e.middleMotor?[e.middleMotor]:[],e.lowerMotor]).map(i=>{let n=this._readout(i);return n?`${this._motorName(i)} ${n}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return c;let i=t.map(h=>this._mainLight(h.bed)).filter(h=>h!==void 0);if(i.length===0)return c;let n=i.filter(h=>this._state(h)?.state==="on").length,r=n===i.length,a=n>0,l=r?"combined.on":a?"combined.mixed":"combined.off",p=f(this.hass,"combined.lights");if(i.some(h=>{let g=this._state(h);return g?.attributes.assumed_state===!0||g?.state!=="on"&&g?.state!=="off"})){let h=this._t("action.off"),g=this._t("action.on");return d`
        ${this._heading("section.lighting")}
        <div class="entity-row combined-entity-row" role="group" aria-label=${p}>
          <ha-icon class="icon" icon="mdi:lightbulb-group-outline"></ha-icon>
          <div class="entity-row-text">
            <span>${p}</span>
          </div>
          <button class="dialog-btn" aria-label=${`${p}: ${h}`}
            @click=${()=>this._setEntities(i,!1)}>${h}</button>
          <button class="dialog-btn" aria-label=${`${p}: ${g}`}
            @click=${()=>this._setEntities(i,!0)}>${g}</button>
        </div>
      `}return d`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${a?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${p}</span>
          <span class="secondary">${f(this.hass,l)}</span>
        </div>
        <button
          class="toggle ${a?"on":""} ${a&&!r?"mixed":""}"
          role="switch"
          aria-label=${p}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(e){let t=e.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return t.length===0?c:d`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${t.map(({pane:i,entityId:n})=>{let r=this._connectionStatus(i.bed),l=this._state(n)?.attributes.rssi;return d`
            <div class="bluetooth-receiver" role="group" aria-label=${i.label}>
            <button
              class="bluetooth-status ${r}"
              @click=${()=>this._moreInfo(n)}
            >
              <ha-icon
                icon=${r==="connected"?"mdi:bluetooth-connect":r==="connecting"?"mdi:bluetooth-transfer":r==="idle"?"mdi:bluetooth":"mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${i.label}</span>
                <span class="bluetooth-detail">
                  ${f(this.hass,`status.${r}`)}${typeof l=="number"?` \xB7 ${l} dBm`:""}
                </span>
              </span>
            </button>
            <div class="tiles">
              ${i.bed.connect?this._tile(i.bed.connect,()=>this._press(i.bed.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):c}
              ${i.bed.disconnect?this._tile(i.bed.disconnect,()=>this._press(i.bed.disconnect),{icon:"mdi:bluetooth-off"}):c}
            </div>
            </div>
          `})}
      </div>
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){return pe(e.lights)}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...j];let t=new Set(j),i=e.filter(r=>t.has(r)),n=j.filter(r=>!i.includes(r));return[...i,...n]}_header(e,t){let i=this._connectionStatus(e),n={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return d`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?c:d`
                <button
                  class="conn ${n[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${f(this.hass,n[i].key)}
                  aria-label=${f(this.hass,n[i].key)}
                >
                  <ha-icon icon=${n[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?d`
      <div class="graphic">
        ${dt(i,t)}
      </div>
    `:c}_graphicState(e){let t=this.hass;if(!t)return;let i=this._config?.show_percentage_graphic===!0,n=e.motors.filter(v=>{let k=v.angle??v.position,M=this._state(k??"")?.attributes.unit_of_measurement;return M==="\xB0"||i&&M==="%"}),r=n.length===0,a=v=>r?ut($e(t,v),i,(k,M)=>this._t(k,M)):gi(v,t,i),l=xe(r?e.motors.filter(v=>a(v)!==void 0):n);if(!l)return;let{upper:p,lower:u}=l,h=this._config?.show_lumbar_graphic===!0,g=h?e.motors.find(v=>v.key==="lumbar"):void 0,y=a(p),b=a(u);if(!y||!b)return;let E=!r&&e.motors.some(v=>{let k=v.cover?this._state(v.cover)?.state:void 0;return k==="opening"||k==="closing"});return{upperMotor:p,showLabels:this._config?.show_graphic_labels!==!1,stackLabels:i||h,lowerMotor:u,middleMotor:g,upper:{label:this._motorName(p),...y},lower:{label:this._motorName(u),...b},middle:g?{label:this._motorName(g),...a(g)}:void 0,moving:E,...r?{estimated:!0}:{}}}_motors(e,t,i,n){let r=t??(e.stop?[e.stop]:[]);if(!gt(e))return c;let a=Fe(e.motors,this._config?.show_lumbar_graphic===!0).filter(Ge),l=mt(e),p=a.length>0||l.length>0||!!e.synchro||!!e.controlSide||!!e.motorExtras?.length,u=n?this._contextEstimates(n):[];return d`
      ${n&&u.length?this._estimateAlertTemplate(n,u):c}
      ${p?this._positionHeading(u):c}
      ${n?.side==="both"?this._estimateOverview(n):c}
      ${e.controlSide?this._moreInfoRow(e.controlSide):c}
      ${e.synchro?this._toggleRow(e.synchro):c}
      ${e.motorExtras?.map(h=>h.startsWith("switch.")?this._switchRow(h):this._moreInfoRow(h))}
      ${a.length?d`<div class="rows">
              ${a.map(h=>this._motorRow(h,e.stop,!1,r,i))}
            </div>`:c}
      ${l.length?d`<div class="rows">
              ${l.map(h=>this._moreInfoRow(h.position))}
            </div>`:c}
      ${e.stop?d`<button class="stop-all" @click=${()=>ce(this._hold,e.stop,r,void 0,this.hass)} ?data-armed=${this._hold.tapMoving}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${f(this.hass,"action.stop_all")}</span>
            </button>`:c}
      ${e.extraStops?.map(h=>d`<button class="stop-all" @click=${()=>ce(this._hold,h,[...r,h],void 0,this.hass)} ?data-armed=${this._hold.tapMoving}>
        <ha-icon icon="mdi:stop"></ha-icon>
        <span>${S(this.hass,h)}</span>
      </button>`)}
    `}_firmness(e){return e.firmness.length===0?c:d`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t,i=!1,n,r){let a=this._hold.tapDirection(e),l=a?f(this.hass,`tap.moving_${a}`):this._readout(e),p=e.position??e.estimate,u=!!e.cover||!!t,h=d`
      <span>${this._motorName(e)}</span>
      ${l&&!i?d`<span class="readout ${a?"moving":""}">${l}</span>`:c}
    `;return d`
      <div class="row">
        ${p?d`<button
              class="row-label position-label"
              @click=${()=>this._moreInfo(p)}
            >${h}</button>`:d`<div class="row-label">${h}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(e,"down",t,n,r):c}
          ${this._motorDirection(e,"up",t,n,r)}
          ${i?c:d`<button
            class="cg-btn"
            aria-label=${f(this.hass,"action.motor_stop",{motor:this._motorName(e)})}
            @click=${()=>this._motorStop(e,t,n)}
            ?disabled=${!u}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?c:this._motorDirection(e,"down",t,n,r)}
        </div>
      </div>
    `}_motorDirection(e,t,i,n,r){let a=e.cover??e[t],l=!!e.cover||!!i,p=!a||!l&&!e.releaseButton||this._config?.layout==="compact"&&(!l||!this._available(a));if(!e.cover&&a&&this.hass?.states[a]?.attributes.requires_confirmation===!0)return d`
        <button class="cg-btn"
          aria-label=${f(this.hass,`action.motor_${t}`,{motor:this._motorName(e)})}
          @click=${()=>this._press(a)}
          ?disabled=${p}
        ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`;if(this._config?.tap_to_move===!0&&St(e,t)){let u=this._hold.tapDirection(e)===t;return d`
        <button class="cg-btn tap ${u?"moving":""}"
          aria-label=${f(this.hass,`action.motor_${t}`,{motor:this._motorName(e)})}
          aria-pressed=${u?"true":"false"}
          @keydown=${h=>{h.repeat&&(h.key==="Enter"||h.key===" ")&&h.preventDefault()}}
          @click=${()=>this._tapMove(e,t,i,n,r)}
          ?disabled=${p&&!u}
        ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}return d`
      <button class="cg-btn"
        aria-label=${f(this.hass,`action.motor_${t}`,{motor:this._motorName(e)})}
        @pointerdown=${u=>this._startHold(u,e,t,i,n,r)}
        @pointerup=${u=>this._endPointerHold(u,e,i)}
        @pointercancel=${u=>this._endPointerHold(u,e,i)}
        @keydown=${u=>this._startHold(u,e,t,i,n,r)}
        @keyup=${u=>this._endKeyHold(u,e,i)}
        @blur=${()=>this._hold.endKeyboard(e,i)}
        @click=${u=>this._activateWithoutPointer(u,e,t,i,n)}
        ?disabled=${p}
      ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}_presets(e){return _t(e)?d`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._actionTile(t,e.stop))}
        ${e.presetSaves.map(t=>this._actionTile(t))}
      </div>
    `:c}_utility(e){return bt(e)?d`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._actionTile(t,e.stop))}
      </div>
      ${e.utilitySwitches?.map(t=>this._switchRow(t))}
      ${e.utilitySelects?.map(t=>this._moreInfoRow(t))}
      ${e.utilityNumbers?.map(t=>this._moreInfoRow(t))}
      ${e.utilityStates?.map(t=>this._moreInfoRow(t))}
    `:c}_actionTile(e,t,i=()=>this._press(e)){let n=Ct(this.hass,e);return n?this._heldActionTile(e,n,t):this._tile(e,i)}_heldActionTile(e,t,i){return d`<button class="tile held"
      aria-label=${S(this.hass,e)}
      @pointerdown=${n=>this._startHold(n,t,"up",i)}
      @pointerup=${n=>this._endPointerHold(n,t,i)}
      @pointercancel=${n=>this._endPointerHold(n,t,i)}
      @keydown=${n=>this._startHold(n,t,"up",i)}
      @keyup=${n=>this._endKeyHold(n,t,i)}
      @blur=${()=>this._endHold(t,i)}
      @click=${n=>this._activateWithoutPointer(n,t,"up",i)}
      ?disabled=${!i||!this._available(e)}>
      ${this._icon(e)}
      <span class="tile-label">${S(this.hass,e)}</span>
    </button>`}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let l=new Set(i.map(Number));t=t.filter(p=>l.has(p.slot))}if(t.length===0)return c;let n=this._config?.memory_save!==!1&&t.some(l=>l.save),r=t.map(l=>l.save??l.goto??String(l.slot)).join("|"),a=this._saveModeFor===r;return d`
      <div class="section-heading heading-row">
        <span>${f(this.hass,"section.memory")}</span>
        ${n?d`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${f(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:c}
      </div>
      ${a?d`<div class="hint">${f(this.hass,"memory.set_hint")}</div>`:c}
      <div class="tiles">${t.map(l=>this._memoryTile(l,a,e.stop))}</div>
    `}_memoryTile(e,t,i){let n=e.goto??e.save;if(t){let a=!!e.save;return d`
        <button
          class="tile ${a?"save-mode":"is-disabled"}"
          ?disabled=${!a}
          @click=${()=>a&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${S(this.hass,n)}</span>
        </button>
      `}let r=!!e.goto;return r?this._actionTile(e.goto,i):d`
      <button
        class="tile ${r?"":"is-disabled"}"
        ?disabled=${!r}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(n)}
        <span class="tile-label">${S(this.hass,n)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;if(!ft(e))return c;let n=i||t.state||t.level||t.numbers?.length||t.timer||t.toggle||t.cycle||t.timerMinutes||t.timerToggle||t.buttons?.length;return d`
      ${this._heading("section.lighting")}
      ${t.mood&&n?this._subheading("lighting.floor"):c}
      ${i?this._switchRow(i):c}
      ${t.switches?.map(r=>this._switchRow(r))}
      ${t.state?this._moreInfoRow(t.state):c}
      ${t.states?.map(r=>this._moreInfoRow(r))}
      ${t.level?this._moreInfoRow(t.level):c}
      ${t.numbers?.map(r=>this._moreInfoRow(r))}
      ${t.timer?this._moreInfoRow(t.timer):c}
      ${t.timerMinutes?this._moreInfoRow(t.timerMinutes):c}
      ${!t.timerAppliesImmediately&&(t.timerMinutes||t.timerToggle)?d`<div class="hint">${f(this.hass,"lighting.timer_pending")}</div>`:c}
      ${t.toggle||t.cycle||t.timerToggle||t.buttons?.length?d`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):c}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):c}
              ${t.timerToggle?this._tile(t.timerToggle,()=>this._press(t.timerToggle)):c}
              ${t.buttons?.map(r=>this._actionTile(r,e.stop))}
            </div>`:c}
      ${t.mood?d`
        ${this._subheading("lighting.mood")}
        ${t.mood.selects.map(r=>this._moreInfoRow(r))}
        ${t.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${t.mood.toggle||t.mood.buttons?.length?d`<div class="tiles">
          ${t.mood.toggle?this._tile(t.mood.toggle,()=>this._press(t.mood.toggle)):c}
          ${t.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:c}
      `:c}
    `}_massage(e){let t=e.massage;return vt(e)?d`
      ${this._heading("section.massage")}
      ${t.buttons.length?d`<div class="tiles">
              ${t.buttons.map(i=>this._actionTile(i,e.stop))}
            </div>`:c}
      ${t.switches?.map(i=>this._switchRow(i))}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.selects?.map(i=>this._moreInfoRow(i))}
      ${t.states?.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):c}
    `:c}_climate(e){let t=yt(e);return t.length===0?c:d`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?c:d`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):c}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):c}
      </div>
    `}_heading(e){return d`<div class="section-heading">${f(this.hass,e)}</div>`}_subheading(e){return d`<div class="lighting-heading">${f(this.hass,e)}</div>`}_tile(e,t,i={}){return d`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${S(this.hass,e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",n=S(this.hass,e);return d`
      <div class="entity-row" @click=${()=>this._moreInfo(e)}>
        <button class="entity-row-details" @click=${r=>{r.stopPropagation(),this._moreInfo(e)}}>
          ${this._icon(e)}
          <div class="entity-row-text">
            <span>${n}</span>
            <span class="secondary">${this._stateText(e)}</span>
          </div>
        </button>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${n}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(e)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_switchRow(e){let t=this._state(e);if(t?.attributes.assumed_state!==!0&&(t?.state==="on"||t?.state==="off"))return this._toggleRow(e);let i=e.split(".",1)[0],n=S(this.hass,e),r=this._t("action.off"),a=this._t("action.on");return d`
      <div class="entity-row" role="group" aria-label=${n}>
        <button class="entity-row-details" aria-label=${n} @click=${()=>this._moreInfo(e)}>
          ${this._icon(e)}
          <span class="entity-row-text">
            <span>${n}</span>
            <span class="secondary">${this._stateText(e)}</span>
          </span>
        </button>
        <button class="dialog-btn" aria-label=${`${n}: ${r}`}
          @click=${()=>this._call(i,"turn_off",e)}>${r}</button>
        <button class="dialog-btn" aria-label=${`${n}: ${a}`}
          @click=${()=>this._call(i,"turn_on",e)}>${a}</button>
      </div>
    `}_moreInfoRow(e){let t=S(this.hass,e);return d`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        @click=${()=>this._moreInfo(e)}
        @keydown=${i=>this._onRowKey(i,()=>this._moreInfo(e))}
      >
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${t}</span>
        </div>
        <span class="secondary value">${this._stateText(e)}</span>
      </div>
    `}_icon(e,t){let i=this._state(e);return i?d`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:d`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return d`<ha-card><div class="notice">${f(this.hass,e)}</div></ha-card>`}_estimateSideKey(e,t){let i=[e.estimateRemote,e.stop,...e.motors.flatMap(n=>[n.estimate,n.reference])];for(let n of i){let r=n?this._state(n)?.attributes.bed_side:void 0;if(r==="left"||r==="right")return r}return t===0?"left":"right"}_t(e,t){return f(this.hass,e,t)}_contextEstimates(e){return e.sides.flatMap(t=>ne(this.hass,t.motors))}_estimatesByKey(e){return Object.fromEntries(e.sides.map(t=>[t.key,ne(this.hass,t.motors)]))}_estimateService(e,t,i={}){return this.hass?.callService(O,e,{device_id:t.deviceId,...t.side?{side:t.side}:{},...i})??Promise.resolve()}_toast(e){this.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:e},bubbles:!0,composed:!0}))}_positionHeading(e){let t=ht(e);return t?d`<div class="section-heading heading-row">
      <span>${this._t("section.position")}</span>
      <span class="estimate-chip chip-${t}">${this._t(`estimate.chip_${t}`)}</span>
    </div>`:this._heading("section.position")}_estimateValues(e){return e.map(t=>`${this._motorName({key:t.motor})} ${I({...t,state:t.percent===void 0?"unknown":"tracking"},(i,n)=>this._t(i,n))}`).join(", ")}_estimateAlertTemplate(e,t){let i=ai(t);if(!i)return c;let n,r,a=d`<button class="set-btn" @click=${()=>this._openReference(e)}>
      ${this._t("estimate.set_reference")}</button>`;if(i.kind==="calibrate")n=this._t("estimate.alert_calibrate"),r=d`<button class="set-btn" @click=${this._openSettings}>
        ${this._t("estimate.calibrate_now")}</button>`;else if(i.kind==="unconfirmed")n=this._t("estimate.alert_unconfirmed",{values:this._estimateValues(i.estimates)}),r=d`<button class="set-btn" @click=${()=>void this._estimateService("estimate_confirm_unchanged",e).catch(()=>{})}>
        ${this._t("estimate.unchanged")}</button>${a}`;else{let l=`estimate.reason_${i.reason??"not_referenced"}`,p=this._t(l);n=this._t("estimate.alert_unknown",{reason:p===l?this._t("estimate.reason_not_referenced"):p}),r=a}return d`<div class="estimate-alert alert-${i.kind}" role="status">
      <ha-icon icon=${i.kind==="calibrate"?"mdi:tune-variant":"mdi:alert-outline"}></ha-icon>
      <span class="estimate-alert-text">${n}</span>
      <div class="estimate-alert-actions">${r}</div>
    </div>`}_estimateOverview(e){let t=e.sides.flatMap(i=>{let n=ne(this.hass,i.motors);return n.length?[{side:i,estimates:n}]:[]});return t.length===0?c:d`<div class="estimate-overview">
      ${t.map(({side:i,estimates:n})=>d`<div class="estimate-overview-row">
        <span class="estimate-overview-side">${i.label}</span>
        ${Ne(n)?d`<span>${n.map(r=>`${this._motorName({key:r.motor})} ${I(r,(a,l)=>this._t(a,l))}`).join(" \xB7 ")}</span>`:d`<span>${this._t("estimate.unknown")} ·
              <button class="link-btn" @click=${()=>this._openReference({deviceId:i.deviceId,paired:!0,sides:[i],savedPositions:e.savedPositions})}>${this._t("estimate.set_reference")}</button></span>`}
      </div>`)}
    </div>`}_savedPositions(e){if(!e.savedPositions)return c;let t=this._contextEstimates(e),i=ci(li(this.hass,e.savedPositions),e.sides.map(l=>l.key));if(t.length===0&&i.length===0)return c;let n=this._estimatesByKey(e),r=this._savedEditFor===e.deviceId,a=Ne(t);return d`
      <div class="section-heading heading-row">
        <span>${this._t("section.saved_positions")}</span>
        ${i.length?d`<button class="set-btn ${r?"active":""}"
              @click=${()=>{this._savedEditFor=r?void 0:e.deviceId}}>
              <ha-icon icon=${r?"mdi:check":"mdi:pencil-outline"}></ha-icon>
              <span>${this._t(r?"estimate.done":"estimate.edit")}</span>
            </button>`:c}
      </div>
      ${r?d`<div class="hint">${this._t("estimate.edit_hint")}</div>`:c}
      <div class="tiles">
        ${i.map(l=>{let p=pi(l,n),u=e.paired?di(l):"bed";return d`<button
            class="tile ${r?"save-mode":""} ${!r&&!p?"is-disabled":""}"
            ?disabled=${!r&&!p}
            @click=${()=>r?this._openEdit(e,l):this._recall(e,l)}>
            <ha-icon class="icon" icon=${r?"mdi:pencil-outline":"mdi:bookmark-outline"}></ha-icon>
            <span class="tile-label">${l.name}</span>
            ${u!=="bed"?d`<span class="tile-sublabel">${this._t(`estimate.scope_${u}`)}</span>`:c}
          </button>`})}
        <button class="tile ${a?"":"is-disabled"}" ?disabled=${!a}
          @click=${()=>{this._estimateDialog={kind:"save",ctx:e,name:"",button:!0}}}>
          <ha-icon class="icon" icon="mdi:bookmark-plus-outline"></ha-icon>
          <span class="tile-label">${this._t("estimate.save")}</span>
        </button>
      </div>
      <div class="hint estimate-footer">${this._t("estimate.footer")}</div>
    `}_recall(e,t){this._hold.abandon(),this._estimateService("estimate_recall_position",{...e,side:void 0},{position:t.id}).then(()=>this._toast(this._t("estimate.recalled",{name:t.name}))).catch(()=>{})}_openReference(e){this._estimateDialog={kind:"reference",ctx:e,choice:"flat",phase:"choose"}}_openEdit(e,t){this._estimateDialog={kind:"edit",ctx:e,position:t,name:t.name,button:t.button}}_stopEstimate(e){this._estimateService("stop_all",e).catch(()=>{})}updated(e){super.updated(e),this._detailsCard&&(this._detailsCard.hass=this.hass);let t=this.renderRoot?.querySelector?.("dialog.estimate-dialog");t&&!t.open&&t.showModal()}_estimateDialogTemplate(){let e=this._estimateDialog;if(!e)return c;let t=e.kind==="confirm"?this._confirmDialog(e.entityId):e.kind==="reference"?this._referenceDialog(e):e.kind==="save"?this._saveDialog(e):this._editDialog(e);return d`<dialog class="estimate-dialog" @close=${this._closeEstimateDialog}>
      ${t}
    </dialog>`}_confirmDialog(e){let t=S(this.hass,e),i=this.hass?.states[e]?.attributes.card_role==="save";return d`
      <p>${this._t(i?"action.confirm":"action.confirm_send",{action:t})}</p>
      <div class="dialog-actions">
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" @click=${()=>{this._closeEstimateDialog(),this._sendPress(e)}}>${t}</button>
      </div>`}_dialogMotors(e){let t=this._contextEstimates(e).filter(i=>i.state!=="not_calibrated").map(i=>i.motor);return[...new Set(t)]}_referenceDialog(e){let t=this._dialogMotors(e.ctx),i=t.map(u=>this._motorName({key:u})).join(", "),n=[{value:"flat",title:this._t("estimate.ref_flat"),detail:this._t(t.length===1?"estimate.ref_flat_detail_one":"estimate.ref_flat_detail",{motors:i})},{value:"lower",title:this._t("estimate.ref_lower"),detail:this._t("estimate.ref_lower_detail")},...t.length>1?t.map(u=>({value:`only:${u}`,title:this._t("estimate.ref_only",{motor:this._motorName({key:u})}),detail:this._t("estimate.ref_only_detail")})):[]],r=e.choice==="lower"&&e.phase==="choose",a=e.choice.startsWith("only:")?[e.choice.slice(5)]:t,l=()=>{if(e.phase!=="lowering"){if(r){let u={...e,phase:"lowering"};this._estimateDialog=u,this._estimateService("lower_to_flat",e.ctx).then(()=>{this._estimateDialog===u&&(this._estimateDialog={...e,phase:"lowered"})},()=>{this._estimateDialog===u&&(this._estimateDialog={...e,phase:"choose"})});return}this._estimateService("estimate_set_reference",e.ctx,{motors:a}).catch(()=>{}),this._estimateDialog=void 0}},p=e.phase==="lowering"?"estimate.ref_lowering_running":e.phase==="lowered"?"estimate.ref_lowering":"estimate.ref_text";return d`
      <h2>${this._t("estimate.ref_title")}</h2>
      <p class="dialog-text">${this._t(p)}</p>
      ${e.phase!=="choose"?c:d`<div class="dialog-choices" role="radiogroup">
        ${n.map(u=>d`<label class="dialog-choice">
          <input type="radio" name="reference" .checked=${e.choice===u.value}
            @change=${()=>{this._estimateDialog={...e,choice:u.value}}} />
          <span><strong>${u.title}</strong><span class="dialog-detail">${u.detail}</span></span>
        </label>`)}
      </div>`}
      <div class="dialog-actions">
        ${e.phase==="lowering"?d`<button class="dialog-btn danger" @click=${()=>{this._stopEstimate(e.ctx),this._estimateDialog={...e,phase:"choose"}}}>${this._t("action.stop")}</button>`:c}
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" ?disabled=${e.phase==="lowering"} @click=${l}>
          ${this._t(r?"estimate.ref_lower_start":"estimate.ref_confirm")}</button>
      </div>`}_estimateList(e){return d`<div class="dialog-values">
      ${e.sides.flatMap(t=>ne(this.hass,t.motors).map(i=>d`
        <div class="dialog-value"><span>${e.paired?`${t.label} `:""}${this._motorName({key:i.motor})}</span>
          <span>${I(i,(n,r)=>this._t(n,r))}</span></div>`))}
    </div>`}_saveDialog(e){let t=e.name.trim(),i=()=>{t&&(this._estimateService("estimate_save_position",e.ctx,{name:t,create_button:e.button}).catch(()=>{}),this._estimateDialog=void 0)};return d`
      <h2>${this._t("estimate.save_title")}</h2>
      <label class="dialog-field"><span>${this._t("estimate.name")}</span>
        <input type="text" maxlength="40" .value=${e.name}
          @input=${n=>{this._estimateDialog={...e,name:n.target.value}}} />
      </label>
      ${this._estimateList(e.ctx)}
      <label class="dialog-check">
        <input type="checkbox" .checked=${e.button}
          @change=${n=>{this._estimateDialog={...e,button:n.target.checked}}} />
        <span><strong>${this._t("estimate.create_button")}</strong>
          <span class="dialog-detail">${this._t("estimate.create_button_detail")}</span></span>
      </label>
      <p class="dialog-text">${this._t("estimate.save_note")}</p>
      <div class="dialog-actions">
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" ?disabled=${!t} @click=${i}>${this._t("estimate.save_confirm")}</button>
      </div>`}_editDialog(e){let{position:t,ctx:i}=e,n=this._estimatesByKey(i),a=Object.keys(t.beds).every(h=>Ne(n[h]??[])),l=e.name.trim(),p=(h,g={})=>{this._estimateService(h,{...i,side:void 0},{position:t.id,...g}).catch(()=>{}),this._estimateDialog=void 0},u=h=>h==="bed"?"":`${this._t(`card.${h}_side`)} `;return d`
      <h2>${this._t("estimate.edit_title",{name:t.name})}</h2>
      <label class="dialog-field"><span>${this._t("estimate.name")}</span>
        <input type="text" maxlength="40" .value=${e.name}
          @input=${h=>{this._estimateDialog={...e,name:h.target.value}}} />
      </label>
      <div class="dialog-values">
        <div class="dialog-value dialog-value-head"><span></span>
          <span>${this._t("estimate.saved")}</span><span>${this._t("estimate.now")}</span></div>
        ${Object.entries(t.beds).flatMap(([h,g])=>Object.entries(g).map(([y,b])=>{let E=n[h]?.find(v=>v.motor===y);return d`<div class="dialog-value">
              <span>${u(h)}${this._motorName({key:y})}</span>
              <span>${Math.round(b)}%</span>
              <span>${E?I(E,(v,k)=>this._t(v,k)):"-"}</span>
            </div>`}))}
      </div>
      <label class="dialog-check">
        <input type="checkbox" .checked=${e.button}
          @change=${h=>{this._estimateDialog={...e,button:h.target.checked}}} />
        <span><strong>${this._t("estimate.create_button")}</strong>
          <span class="dialog-detail">${this._t("estimate.create_button_detail")}</span></span>
      </label>
      ${a?c:d`<p class="dialog-text">${this._t("estimate.update_blocked")}</p>`}
      <div class="dialog-actions">
        <button class="dialog-btn danger" @click=${()=>p("estimate_delete_position")}>${this._t("estimate.delete")}</button>
        <button class="dialog-btn" ?disabled=${!a} @click=${()=>p("estimate_update_position")}>${this._t("estimate.update")}</button>
        <button class="dialog-btn primary" ?disabled=${!l}
          @click=${()=>p("estimate_rename_position",{name:l,create_button:e.button})}>${this._t("estimate.save_confirm")}</button>
      </div>`}_state(e){return this.hass?.states[e]}_title(e=this._config?.device_id){return this._config?.name?this._config.name:D(this.hass,e)??f(this.hass,"card.default_name")}_motorName(e){let t=`motor.${e.key}`,i=f(this.hass,t);if(i!==t)return i;let n=e.key.split("_").map(a=>a.charAt(0).toUpperCase()+a.slice(1)).join(" "),r=e.cover??e.nameFrom;return r?S(this.hass,r,n):n}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){let t=e.angle??e.position;if(t){let n=this._angle(e);if(n===void 0)return;let r=this._state(t)?.attributes.unit_of_measurement,a=e.angle?"\xB0":"%";return`${Math.round(n)}${typeof r=="string"?r:a}`}let i=$e(this.hass,e);if(i)return I(i,(n,r)=>f(this.hass,n,r));if(e.cover){let n=this._state(e.cover)?.attributes.current_position;return typeof n=="number"?`${Math.round(n)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position,i.estimate,i.reference].forEach(n=>n&&t.add(n));[e.estimateRemote,e.savedPositions].forEach(i=>i&&t.add(i)),[...e.presets,...e.presetSaves].forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(n=>n&&t.add(n));return[e.stop,e.synchro,e.controlSide,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.state,...e.lights.states??[],e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.lights.timerMinutes,e.lights.timerToggle,e.lights.mood?.toggle,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),[...e.extraStops??[],...e.motorExtras??[]].forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.lights.buttons?.forEach(i=>t.add(i)),e.lights.numbers?.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.massage.selects?.forEach(i=>t.add(i)),e.massage.states?.forEach(i=>t.add(i)),e.massage.switches?.forEach(i=>t.add(i)),e.lights.switches?.forEach(i=>t.add(i)),e.lights.mood?.selects.forEach(i=>t.add(i)),e.lights.mood?.numbers.forEach(i=>t.add(i)),e.lights.mood?.buttons?.forEach(i=>t.add(i)),e.utility.forEach(i=>t.add(i)),e.utilityNumbers?.forEach(i=>t.add(i)),e.utilitySelects?.forEach(i=>t.add(i)),e.utilityStates?.forEach(i=>t.add(i)),e.utilitySwitches?.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),e.climate.numbers.forEach(i=>t.add(i)),[...t]}_startHold(e,t,i,n,r,a){let l=null;if(e instanceof KeyboardEvent){if(e.key!=="Enter"&&e.key!==" "||(e.preventDefault(),e.repeat))return}else{if(e.button!==0||!e.isPrimary)return;e.currentTarget.setPointerCapture?.(e.pointerId),e.preventDefault(),l=e.pointerId}if(this._hold.tapMoving){this._hold.endTap();return}this._markCompactTarget(t,n),this._hold.start(t,i,l,n,r??(n?[n]:[]),a,e instanceof KeyboardEvent?e.key:null,ee(this.hass,n??t.holdEntityId??t.cover??t[i]))}_activateWithoutPointer(e,t,i,n,r){if(e.detail===0){if(this._hold.tapMoving){this._hold.endTap();return}this._hold.heldKey===null&&(this._markCompactTarget(t,n),this._hold.claimStopScope([...r??[],...n?[n]:[],...t.cover?[t.cover]:[]],ee(this.hass,n??t.holdEntityId??t.cover??t[i])),Mt(this.hass,t,i))}}_tapMove(e,t,i,n,r){this._hold.tapMoving||this._markCompactTarget(e,i),this._hold.tap(e,t,i,n??(i?[i]:[]),r,ee(this.hass,i??e.holdEntityId??e.cover??e[t]))}_markCompactTarget(e,t){this._config?.layout==="compact"&&(t?this._compactStopTargets.set(t,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate())}_endPointerHold(e,t,i){this._hold.endFromPointer(t,e.pointerId,e.type!=="pointerup"||e.button===0,i)}_endKeyHold(e,t,i){e.key!=="Enter"&&e.key!==" "||(e.stopPropagation(),this._hold.endKeyboard(t,i,e.key))}_endHold(e,t){this._hold.end(e,t)}_motorStop(e,t,i){if(this._hold.tapMoving&&this._hold.tapDirection(e)===void 0&&this._hold.endTap(),e.cover){i?.length?ce(this._hold,e.cover,[...i,e.cover],e.coverStopScope==="side"?void 0:e.key,this.hass):(this._hold.stopCover(e,ee(this.hass,e.cover),e.coverStopScope??"motor",t,Xe(this.hass,e.cover)),this._cover(e.cover,"stop_cover"));return}ce(this._hold,t,i,void 0,this.hass)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){if(this.hass?.states[e]?.attributes.requires_confirmation===!0){this._estimateDialog={kind:"confirm",entityId:e};return}this._sendPress(e)}_sendPress(e){this._hold.retireTap(),this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};P.styles=ue`
    .bed-details-dialog {
      box-sizing: border-box;
      width: min(560px, calc(100vw - 24px));
      max-height: calc(100dvh - 32px);
      padding: 0;
      overflow: auto;
      color: var(--primary-text-color);
      background: var(--card-background-color, #fff);
      border: 1px solid var(--divider-color);
      border-radius: 16px;
      box-shadow: 0 16px 60px #0006;
    }
    .bed-details-dialog::backdrop { background: #0009; }
    .bed-details-heading {
      position: sticky; top: 0; z-index: 1;
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; padding: 8px 16px;
      background: var(--card-background-color, #fff);
      border-bottom: 1px solid var(--divider-color);
    }
    .bed-details-close {
      border: 0; background: transparent; color: inherit;
      width: 44px; height: 44px; font-size: 20px; cursor: pointer;
    }
    .bed-details-content { padding: 8px; }
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
    .compact-graphic { position: relative; display: block; box-sizing: border-box; width: 100%; padding: 0;
      border: 0; border-radius: 8px; background: none; color: var(--primary-text-color); }
    button.compact-graphic { cursor: pointer; }
    .compact-estimate-chip { position: absolute; top: 0; right: 0; }
    .compact-graphic .bed-graphic { display: block; width: 100%; height: 132px; max-width: 300px; margin: auto; }
    .compact-glance .compact-graphic .bed-graphic { height: 112px; }
    .compact-no-position { min-height: 90px; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 8px; font-size: .75rem;
      color: var(--secondary-text-color); }
    .compact-no-position ha-icon { --mdc-icon-size: 36px; }
    .compact-readouts { display: flex; justify-content: space-between; gap: 8px;
      padding: 0 2px 12px; font-size: 11px; line-height: 17px; color: var(--secondary-text-color); }
    .compact-readouts > div { min-width: 0; display: flex; align-items: center; gap: 5px; }
    .compact-side-name { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
    .compact-side-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden;
      clip-path: inset(50%); white-space: nowrap; }
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
      :host .pane { animation: none; }
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
    /* How a panel's position is known (#601). Only measured feedback is solid.
       Set per panel, so a lumbar section follows the same rule. */
    .bed-panel.is-estimated .bed-surface,
    .dual-bed-panel.is-estimated .dual-bed-surface {
      fill-opacity: 0.45;
      stroke-width: 1.5;
      stroke-dasharray: 5 4;
    }
    .bed-panel.is-estimated .bed-surface { stroke: rgb(var(--ab-graphic-rgb)); }
    .dual-bed-panel.is-estimated .dual-bed-surface { stroke: currentColor; }
    .is-unconfirmed .bed-surface,
    .is-unconfirmed .dual-bed-surface {
      fill: var(--secondary-text-color);
      fill-opacity: 0.3;
      stroke: var(--secondary-text-color);
      stroke-width: 1.5;
      stroke-dasharray: 5 4;
    }
    .is-unknown .bed-surface,
    .is-unknown .dual-bed-surface {
      fill-opacity: 0.08;
      stroke: var(--secondary-text-color);
      stroke-width: 1.5;
      stroke-dasharray: 1 3;
      stroke-linecap: round;
    }
    .estimate-chip {
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 0.66rem;
      letter-spacing: 0.06em;
      background: color-mix(in srgb, var(--primary-color) 16%, transparent);
      color: var(--primary-color);
    }
    .estimate-chip.chip-unconfirmed,
    .estimate-chip.chip-unknown {
      background: color-mix(in srgb, var(--warning-color, #ffa600) 18%, transparent);
      color: var(--warning-color, #ffa600);
    }
    .estimate-alert {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 6px 10px;
      align-items: start;
      margin: 10px 2px 2px;
      padding: 10px 12px;
      border-radius: 9px;
      background: color-mix(in srgb, var(--warning-color, #ffa600) 12%, transparent);
      color: var(--primary-text-color);
      font-size: 0.82rem;
      --mdc-icon-size: 20px;
    }
    .estimate-alert.alert-calibrate {
      background: color-mix(in srgb, var(--primary-color) 12%, transparent);
    }
    .estimate-alert > ha-icon {
      color: var(--warning-color, #ffa600);
    }
    .estimate-alert.alert-calibrate > ha-icon {
      color: var(--primary-color);
    }
    .estimate-alert-actions {
      grid-column: 2;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .estimate-overview {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 0 6px 8px;
      font-size: 0.82rem;
    }
    .estimate-overview-row {
      display: flex;
      gap: 10px;
    }
    .estimate-overview-side {
      font-weight: 600;
      min-width: 3.5em;
    }
    .link-btn {
      border: none;
      background: none;
      padding: 0;
      color: var(--primary-color);
      font: inherit;
      cursor: pointer;
      text-decoration: underline;
    }
    .tile-sublabel {
      font-size: 0.68rem;
      color: var(--secondary-text-color);
    }
    .estimate-dialog {
      box-sizing: border-box;
      width: min(92vw, 420px);
      border: none;
      border-radius: 16px;
      padding: 20px;
      background: var(--card-background-color, var(--primary-background-color));
      color: var(--primary-text-color);
      font-size: 0.9rem;
    }
    .estimate-dialog::backdrop {
      background: rgba(0, 0, 0, 0.5);
    }
    .estimate-dialog h2 {
      margin: 0 0 8px;
      font-size: 1.15rem;
      font-weight: 500;
    }
    .dialog-text,
    .dialog-detail {
      color: var(--secondary-text-color);
    }
    .dialog-detail {
      display: block;
      font-size: 0.8rem;
    }
    .dialog-choices {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 10px 0;
    }
    .dialog-choice,
    .dialog-check {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      cursor: pointer;
    }
    .dialog-check {
      margin: 12px 0 4px;
    }
    .dialog-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 8px 0;
    }
    .dialog-field input {
      font: inherit;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid var(--divider-color);
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
    }
    .dialog-values {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 10px 0;
    }
    .dialog-value {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 12px;
    }
    .dialog-value-head {
      color: var(--secondary-text-color);
      font-size: 0.78rem;
    }
    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }
    .dialog-btn {
      font: inherit;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid var(--divider-color);
      background: none;
      color: var(--primary-color);
      cursor: pointer;
    }
    .dialog-btn.primary {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .dialog-btn.danger {
      color: var(--error-color);
      margin-right: auto;
    }
    .dialog-btn:disabled {
      opacity: 0.4;
      cursor: default;
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
    /* A tap move starts on click, so a drag that begins on the arrow may
       scroll the page instead. */
    .cg-btn.tap {
      touch-action: manipulation;
    }
    .cg-btn.moving,
    .cg-btn.moving:hover {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .row-label .readout.moving {
      color: var(--primary-color);
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
    .stop-all:active,
    .stop-all[data-armed] {
      border-color: var(--error-color);
    }
    /* A tap move is running and waits for a tap to stop it. */
    .stop-all[data-armed] {
      background: color-mix(in srgb, var(--error-color) 12%, var(--ab-control-surface));
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
    /* A held tile is press-and-hold like the motor arrows: a small drag must
       not scroll the page and cancel the hold. */
    .tile.held {
      touch-action: none;
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
    .entity-row-details {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
      min-width: 0;
      padding: 0;
      border: none;
      background: none;
      color: inherit;
      font: inherit;
      text-align: start;
      cursor: pointer;
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
  `,C([re({attribute:!1})],P.prototype,"hass",2),C([R()],P.prototype,"_config",2),C([R()],P.prototype,"_saveModeFor",2),C([R()],P.prototype,"_activePairedPane",2),C([R()],P.prototype,"_synchronizingTo",2),C([R()],P.prototype,"_synchronizationFailed",2),C([R()],P.prototype,"_estimateDialog",2),C([R()],P.prototype,"_savedEditFor",2),C([R()],P.prototype,"_tapRevision",2),C([R()],P.prototype,"_detailsOpen",2);He("adjustable-bed-card",P);console.info(`%c adjustable-bed-card %c ${xi} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{P as AdjustableBedCard};
