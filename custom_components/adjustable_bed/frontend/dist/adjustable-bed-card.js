/* adjustable-bed-card 4.3.0 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var ei=Object.defineProperty;var ti=Object.getOwnPropertyDescriptor;var T=(n,s,e,t)=>{for(var i=t>1?void 0:t?ti(s,e):s,o=n.length-1,r;o>=0;o--)(r=n[o])&&(i=(t?r(s,e,i):r(i))||i);return t&&i&&ei(s,e,i),i};function ye(n,s,e=n?.entities[s]?.device_id){let t=n?.states[s]?.attributes,i=t?.hold_lease_mode;if(i!=="stream"&&i!=="latched"||!e)return;let o=t?.hold_lease_motor,r=t?.bed_side;return{deviceId:e,...typeof o=="string"&&o?{motor:o}:{},...r==="left"||r==="right"||r==="both"?{side:r}:{}}}function ve(n,s){return n.holdLease?n.heldControls?.[s]??n.heldControl?!!n.deviceId:!!(n.timedMove??n.holdLease.motor):!1}var ii=3e4;function ht(n,s){return!(n.heldControls?.[s]??n.heldControl)||ve(n,s)}function ut(n,s,e,t){if(!ve(s,e)||!s.holdLease)return;if(s.heldControls?.[e]??s.heldControl)return Fe(n,s,e,t);let i=s.timedMove??{deviceId:s.holdLease.deviceId,motor:s.holdLease.motor,side:s.holdLease.side};return n?.callService("adjustable_bed","timed_move",{device_id:i.deviceId,...i.side?{side:i.side}:{},motor:i.motor,direction:e,duration_ms:750,hold_owner:t.owner,hold_generation:t.generation})}function ze(n,s){let e=n?.entities[s],t=n?.states[s]?.attributes,i=t?.hold_release_button_key;if(!e?.device_id||typeof i!="string")return;let o=t?.bed_side,r=(o==="left"||o==="right")&&e.translation_key?.endsWith(`_${o}`)?`${i}_${o}`:i;return Object.values(n?.entities??{}).find(c=>c.device_id===e.device_id&&c.entity_id.startsWith("button.")&&c.translation_key===r)?.entity_id}function mt(n,s){let e=n?.entities[s]?.device_id,t=n?.states[s]?.attributes,i=t?.held_control,o=t?.hold_start_delay_ms,r=t?.hold_release_delay_ms;if(!e||typeof i!="string"||typeof o!="number"||!Number.isFinite(o)||o<0||typeof r!="number"||!Number.isFinite(r)||r<0)return;let c=ze(n,s);if(typeof t?.hold_release_button_key=="string"&&!c)return;let l=ye(n,s,e);return{...c?{releaseButton:c}:{},...l?{holdLease:l}:{},key:s,up:s,deviceId:e,holdEntityId:s,heldControl:{control:i,startDelayMs:o,releaseDelayMs:r}}}function Ne(n,s,e){if(s.timedMove)return n?.callService("adjustable_bed","timed_move",{device_id:s.timedMove.deviceId,...s.timedMove.side?{side:s.timedMove.side}:{},motor:s.timedMove.motor,direction:e,duration_ms:1e3});if(s.cover)return n?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:s.cover});let t=e==="up"?s.up:s.down;return t?n?.callService("button","press",{entity_id:t}):void 0}function Fe(n,s,e,t){let i=s.heldControls?.[e]??s.heldControl;if(!i||!s.deviceId)return;let o=n?.states[s.holdEntityId??s.cover??""]?.attributes.bed_side,r={device_id:[s.deviceId],control:i.control,duration:t?750/1e3:60,...t?{hold_owner:t.owner,hold_generation:t.generation}:{}};return(o==="left"||o==="right"||o==="both")&&(r.side=o),n?.callService("adjustable_bed","hold_control",r)}function gt(n,s,e){Ne(n,s,e)?.catch(()=>{})}function _t(n,s,e,t){let i=()=>t(),o=()=>{e()&&t()};n.addEventListener("blur",i),s.addEventListener("visibilitychange",o);let r=!0;return()=>{r&&(r=!1,n.removeEventListener("blur",i),s.removeEventListener("visibilitychange",o))}}function ft(n,s){let e=s[n]?.parent_device_id??s[n]?.via_device_id;return e&&s[e]?e:void 0}function si(n,s){return Object.values(s).some(e=>(e.parent_device_id??e.via_device_id)===n)}var vt={stop_left:"left",stop_right:"right",stop_both:"both"};function fe(n,s){let e=n.states[s]?.attributes,t=e?.bed_side??e?.side,i=t==="left"||t==="right"||t==="both"?t:void 0,o=n.entities[s]?.translation_key,r=o?vt[o]:void 0;if(!(i&&r&&i!==r))return i??r}function pt(n,s){let e=n.entities[s];return e?.platform==="adjustable_bed"&&s.startsWith("button.")&&(e.translation_key==="stop"||e.translation_key!==void 0&&e.translation_key in vt)}function U(n,s){if(!n||!s)return;let e=n.entities[s]?.device_id;if(!e)return;let t=n.devices??{},i=ft(e,t),o=fe(n,s)??(!i&&si(e,t)?"both":void 0);return{deviceId:i&&o?i:e,side:o,physicalDeviceId:e,...i?{parentDeviceId:i}:{},...o==="both"?{physicalChildIds:Object.entries(t).filter(([,r])=>(r.parent_device_id??r.via_device_id)===e).map(([r])=>r)}:{}}}function oi(n,s){return(n.parentDeviceId??n.deviceId)!==(s.parentDeviceId??s.deviceId)?!1:n.side==="both"||s.side==="both"?!0:n.side&&s.side?n.side===s.side:!n.physicalDeviceId||!s.physicalDeviceId||n.physicalDeviceId===s.physicalDeviceId}function Ke(n,s){if(!n||!s)return[];let e=n.entities[s]?.device_id;if(!e)return[];let t=fe(n,s);if(t==="left"||t==="right"){let u=t==="left"?"right":"left",m=Object.values(n.entities).filter(g=>g.entity_id!==s&&g.device_id===e&&pt(n,g.entity_id)&&fe(n,g.entity_id)===u);if(m.length===1)return[m[0].entity_id]}let i=n.devices??{},o=ft(e,i);if(!o)return[];let r=Object.entries(i).filter(([,u])=>(u.parent_device_id??u.via_device_id)===o).map(([u])=>u);if(r.length!==2||!r.includes(e))return[];let c=r.find(u=>u!==e),l=Object.values(n.entities).filter(u=>{if(u.device_id!==c||!pt(n,u.entity_id))return!1;let m=fe(n,u.entity_id);return m!=="both"&&(m===void 0||m!==t)});return l.length===1?[l[0].entity_id]:[]}function _e(n){let s=n.holdEntityId??n.cover??n.up??n.down??"";return`${n.key}\0${s}`}var be=class{constructor(s,e={setTimeout:(t,i)=>globalThis.setTimeout(t,i),clearTimeout:t=>globalThis.clearTimeout(t)}){this.actions=s;this.timers=e;this._key=null;this._motor=null;this._scopeStops=[];this._remainingStops=[];this._stopTargetGenerations=new Map;this._keyboardKey=null;this._motorId=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0;this._repeatBlocked=!1;this._tapDirection=null;this._leaseOwner=`card-${Math.random().toString(36).slice(2,12)}`;this._started=!1;this._releaseId=0;this._pendingReleases=new Map}get heldKey(){return this._key}start(s,e,t,i,o=i?[i]:[],r=[],c=null,l){if(this._key!==null)return;let u=Array.isArray(o)?o:[];this._target=Array.isArray(o)?l:o,this._flushPendingForTarget(i??s.cover??s.key),this._key=s.key,this._motor=Object.freeze({...s,...s.timedMove?{timedMove:Object.freeze({...s.timedMove})}:{}}),this._motorId=_e(s),this._cover=s.cover??null,this._stop=i??null,this._scopeStops=[...new Set([...u,...i?[i]:[],...s.cover?[s.cover]:[],...this._targetScope(this._target)])],this._remainingStops=[...new Set(r)],this.claimStopScope(this._scopeStops),this._pointerId=t,this._keyboardKey=c;let m=++this._generation;this._heldControl=s.heldControls?.[e]??s.heldControl,this._releaseButton=s.releaseButton;let g=this.actions.lease!==void 0&&ve(s,e);if(this._heldControl){let v=this._heldControl.startDelayMs;v<=0?this._startHeldControl(this._motor,e,m,g):this._startTimer=this.timers.setTimeout(()=>this._startHeldControl(this._motor??s,e,m,g),v);return}this._started=!0,g?this._leaseHold(this._motor,e,m):this._repeat(this._motor,e,m)}get tapMoving(){return this._tapDirection!==null}tapDirection(s){return this._tapDirection!==null&&this._motorId===_e(s)?this._tapDirection:void 0}tap(s,e,t,i=t?[t]:[],o=[],r){if(this._tapDirection!==null){this.endTap();return}if(this._key!==null||(s.heldControls?.[e]??s.heldControl)&&!(this.actions.lease&&ve(s,e))||(this._tapDirection=e,this.start(s,e,null,t,i,o,null,r),this._tapDirection===null))return;let l=this._generation;this._tapTimer=this.timers.setTimeout(()=>{l===this._generation&&this.endTap()},ii),this.actions.changed?.()}endTap(){this._tapDirection!==null&&this._motor&&this.end(this._motor)}_targetScope(s){if(!s)return[];let e=s.side==="left"||s.side==="right"?[s.side]:["left","right"];return[...new Set([s.deviceId,...s.physicalDeviceId?[s.physicalDeviceId]:[],...s.physicalChildIds??[]])].flatMap(i=>e.map(o=>`target:${i}:${o}`))}claimStopScope(s,e){for(let t of new Set([...s,...this._targetScope(e)]))this._stopTargetGenerations.set(t,(this._stopTargetGenerations.get(t)??0)+1)}_startHeldControl(s,e,t,i){this._startTimer=void 0,!(t!==this._generation||this._motorId!==_e(s))&&(this._started=!0,i?this._leaseHold(s,e,t):this._holdControl(s,e,t))}_leaseHold(s,e,t){let i={owner:this._leaseOwner,generation:t},o=!0,r=()=>{o=!1,t===this._generation&&(this._renewTimer!==void 0&&(this.timers.clearTimeout(this._renewTimer),this._renewTimer=void 0),this.endTap())},c=this.actions.lease?.(s,e,i);if(!c)return;c.then(r,r);let l=()=>{this._renewTimer=void 0,!(!o||t!==this._generation||this._repeatBlocked)&&(this.actions.lease?.(s,e,i)?.catch(r),this._renewTimer=this.timers.setTimeout(l,250))};this._renewTimer=this.timers.setTimeout(l,250)}async _holdControl(s,e,t){try{let i=this.actions.holdControl?.(s,e);i&&await i}catch{}finally{t===this._generation&&this._reset()}}async _repeat(s,e,t){let i=this._motor;if(i)try{for(;t===this._generation&&!this._repeatBlocked;){let o=this.actions.pulse(i,e);if(!o)return;this._pulseInFlight=o;try{await o}finally{this._pulseInFlight===o&&(this._pulseInFlight=void 0)}}}catch{}finally{t===this._generation&&this.endTap()}}_targetKey(s=this._stop??void 0,e=this._cover??void 0){return s??e??this._key??""}_release(s){return s.releaseButton?(this.actions.stopBed(s.releaseButton),s.releaseButton):s.cover?(this.actions.stopCover(s.cover,s.stopEntityId),s.cover):(this.actions.stopBed(s.stopEntityId),s.stopEntityId)}_scheduleRelease(){let s={id:++this._releaseId,releaseButton:this._releaseButton,motorKey:this._key??"",targetKey:this._targetKey(),target:this._target,cover:this._cover??void 0,stopEntityId:this._stop??void 0,scopeGenerations:new Map(this._scopeStops.map(t=>[t,this._stopTargetGenerations.get(t)??0]))};this._pendingReleases.set(s.id,s);let e=this._heldControl?.releaseDelayMs??0;if(e<=0){this._runRelease(s);return}s.timer=this.timers.setTimeout(()=>this._runRelease(s),e)}_runRelease(s){if(this._pendingReleases.delete(s.id)&&(s.timer!==void 0&&this.timers.clearTimeout(s.timer),[...s.scopeGenerations].every(([e,t])=>this._stopTargetGenerations.get(e)===t)))return this._release(s)}_flushPendingForTarget(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s&&(this._runRelease(t),e.add(i))}return e}_flushAllReleases(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s?(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer)):(this._runRelease(t),e.add(i))}return e}_targetsOverlap(s,e,t,i){return t!==void 0&&s===t?!0:!!e&&!!i&&oi(e,i)}_discardReleasesOverlapping(s,e){let t=!1;for(let i of[...this._pendingReleases.values()])!i.scopeGenerations.has(s)&&!this._targetsOverlap(i.targetKey,i.target,s,e)||(this._pendingReleases.delete(i.id),i.timer!==void 0&&this.timers.clearTimeout(i.timer),i.target?.side==="both"&&[...i.scopeGenerations].every(([o,r])=>this._stopTargetGenerations.get(o)===r)&&(t=!0));return t}_discardAllReleases(){for(let s of this._pendingReleases.values())s.timer!==void 0&&this.timers.clearTimeout(s.timer);this._pendingReleases.clear()}endFromPointer(s,e,t,i){this._pointerId===null||e!==this._pointerId||t&&(i!==void 0&&this._stop!==i||this.end(s,i))}endActiveFromPointer(s,e){!this._motor||this._pointerId===null||this.endFromPointer(this._motor,s,e)}endKeyboard(s,e,t){this._pointerId!==null||this._tapDirection!==null||!this._motor||s&&!this._ownsRelease(s,e)||e!==void 0&&this._stop!==e||t!==void 0&&this._keyboardKey!==null&&this._keyboardKey!==t||this.end(this._motor)}end(s,e){if(!this._ownsRelease(s,e))return;let t=this._started,i=this._heldControl!==void 0,o={releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0};t&&i&&this._scheduleRelease(),this._reset(),!(!t||i)&&this._release(o)}_ownsRelease(s,e){return this._key!==s.key?!1:e===void 0?this._motorId===_e(s):this._stop===e}cancel(s,e=!1){if(!s)return!1;let t=this._key===s.key;t&&this._reset();let i=!1;if(e)for(let o of[...this._pendingReleases.values()])o.motorKey===s.key&&(this._pendingReleases.delete(o.id),o.timer!==void 0&&this.timers.clearTimeout(o.timer),i=!0);return t||i}stopCover(s,e,t,i,o=[]){let r=s.cover;if(!r)return;let c=e!==void 0&&e.side!=="both",l=new Set,u=new Map,m,g=y=>{for(let $ of y)$!==i&&(l.add($),u.set($,this._stopTargetGenerations.get($)??0))};if(this._key!==null&&(t==="side"||this._key===s.key)&&(r===this._cover||i!==void 0&&this._scopeStops.includes(i)||this._targetsOverlap(this._targetKey(),this._target,r,e))){let y=this._target?.side==="both"&&c||i!==void 0&&this._remainingStops.includes(i);this._started&&y&&(i&&g(this._remainingStops),this._heldControl&&g(o)),m=this._pulseInFlight,y&&!this._heldControl&&l.size===0?this._repeatBlocked=!0:this._reset()}for(let y of[...this._pendingReleases.values()]){let $=y.target?.side==="both"&&y.target.deviceId===e?.deviceId&&(e?.side==="left"||e?.side==="right");t!=="side"&&$||t!=="side"&&y.motorKey!==s.key||!(y.cover===r||i!==void 0&&y.scopeGenerations.has(i)||this._targetsOverlap(y.targetKey,y.target,r,e))||(this._pendingReleases.delete(y.id),y.timer!==void 0&&this.timers.clearTimeout(y.timer),c&&y.target?.side==="both"&&[...y.scopeGenerations].every(([b,f])=>this._stopTargetGenerations.get(b)===f)&&g(o))}let v=this._key!==null?this._stop:null,x=()=>{for(let y of l)y!==v&&(this._stopTargetGenerations.get(y)??0)===u.get(y)&&this.actions.stopBed(y)};m?m.then(x,x):x()}stopAll(s,e,t,i=[]){let o=s??this._stop??void 0,r=this._key!==null&&this._started?{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0}:void 0,c=typeof t=="object"?t:void 0,l=typeof t=="string"?t:void 0,u=[...new Set([...Array.isArray(e)?e:o?[o]:this._scopeStops,...this._targetScope(c),...o?[o]:[]])],m=e===!0&&!c,g=l===void 0||l===this._key||o===this._cover,v=this._key!==null&&g&&(m||u.length===0||this._scopeStops.some(f=>u.includes(f))||this._targetsOverlap(this._targetKey(),this._target,o,c)),x=!1;s!==void 0&&(m?this._discardAllReleases():x=this._discardReleasesOverlapping(s,c)),x||=v&&this._started&&this._heldControl!==void 0&&this._target?.side==="both";let y=[...new Set([...v&&this._started?this._remainingStops:[],...x?i:[]])].filter(f=>!u.includes(f)&&f!==this._stop),$=v?this._pulseInFlight:void 0,b=new Map(y.map(f=>[f,this._stopTargetGenerations.get(f)??0]));if(v&&this._reset(),s===void 0){let f=this._flushAllReleases(),d=r?.stopEntityId??r?.cover;r&&(d===void 0||!f.has(d))?this._release(r):!r&&f.size===0&&this.actions.stopBed(o)}else this.actions.stopBed(s);if(y.length>0){let f=()=>{for(let d of y)(this._stopTargetGenerations.get(d)??0)===b.get(d)&&this.actions.stopBed(d)};$?$.then(f,f):f()}}abandon(){let s=this._key===null?null:{releaseButton:this._releaseButton,cover:this._cover??void 0,stopEntityId:this._stop??void 0},e=this._started;this._reset();let t=new Set,i=o=>{o!==void 0&&t.add(o)};s&&e&&i(this._release(s));for(let o of[...this._pendingReleases.values()])i(this._runRelease(o));return[...t]}releaseOnFocusLoss(){this.abandon()}cancelForStopScope(s){let e=!1;for(let t of[...this._pendingReleases.values()])s.includes(t.targetKey)&&(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer),e=!0);return this._key!==null&&this._scopeStops.some(t=>s.includes(t))&&(this._reset(),e=!0),e}_reset(){this._startTimer!==void 0&&this.timers.clearTimeout(this._startTimer),this._startTimer=void 0,this._renewTimer!==void 0&&this.timers.clearTimeout(this._renewTimer),this._renewTimer=void 0,this._tapTimer!==void 0&&this.timers.clearTimeout(this._tapTimer),this._tapTimer=void 0;let s=this._tapDirection!==null;this._tapDirection=null,this._key=null,this._motor=null,this._scopeStops=[],this._remainingStops=[],this._keyboardKey=null,this._pulseInFlight=void 0,this._motorId=null,this._cover=null,this._stop=null,this._target=void 0,this._pointerId=null,this._repeatBlocked=!1,this._started=!1,this._heldControl=void 0,this._releaseButton=void 0,this._generation++,s&&this.actions.changed?.()}};function bt(n,s,e){let t=()=>{n.abandon()},i=()=>{s.visibilityState==="hidden"&&t()};return s.addEventListener("visibilitychange",i),e.addEventListener("pagehide",t),()=>{s.removeEventListener("visibilitychange",i),e.removeEventListener("pagehide",t)}}function xe(n,s,e,t,i){n.stopAll(s,e??(s?[s]:void 0),t??U(i,s),Ke(i,s))}function L(n,s){let e=s?n?.devices[s]:void 0;return(e?.name_by_user||e?.name)?.trim()||void 0}function M(n,s,e=s){let t=n?.states[s];if(t&&n?.formatEntityName)return n.formatEntityName(t,{type:"entity"})||e;let i=n?.entities[s],o=t?.attributes.friendly_name||i?.name,r=L(n,i?.device_id);return o&&r&&o.startsWith(`${r} `)?o.slice(r.length+1)||e:o||e}var D="adjustable_bed";function ie(n){for(let s of["left","right","both"]){let e=`_${s}`;if(n.endsWith(e))return{key:n.slice(0,-e.length),side:s}}return{key:n}}var q=["graphic","motors","firmness","presets","saved_positions","memory","lighting","massage","utility","climate","connection"],yt=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],We=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_reading","preset_swing","preset_incline","preset_both_up","preset_yoga"],ni={back:"back",foot:"feet",pillow:"pillow"},ri=new Set(["elevate_both","starcode_m1x12_part_1","starcode_m1x12_part_2","starcode_m1x12_part_4","starcode_m1x12_part_8","starcode_m1x12_part_16"]),ai=n=>n.split(".",1)[0],Ge=n=>n.translation_key??"";function li(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[],utilityStates:[]}}function A(n,s,e){let t=li();if(!s||!n?.entities)return t;let i=()=>t.lights.mood??={selects:[],numbers:[]},o=n.devices?.[s]?.parent_device_id||Object.values(n.devices??{}).some(f=>f.parent_device_id===s),r=Object.values(n.entities).filter(f=>f.device_id===s&&f.platform===D),c=!!e||!!o&&!r.some(f=>f.translation_key==="ble_connection"),l=new Map,u=f=>{let d=l.get(f);return d||(d=ri.has(f)?{key:f,coverStopScope:"side"}:{key:f},l.set(f,d)),d},m=(f,d,ge,z)=>{let k=u(d);k[ge]=f;let Oe=ye(n,f,z??s);Oe&&(k.holdLease=Oe);let H=n.states[f]?.attributes,a=H?.held_control,w=H?.hold_start_delay_ms,S=H?.hold_release_delay_ms;typeof a=="string"&&typeof w=="number"&&Number.isFinite(w)&&w>=0&&typeof S=="number"&&Number.isFinite(S)&&S>=0&&z&&(k.deviceId=z,k.holdEntityId=f,k.heldControls={...k.heldControls,[ge]:{control:a,startDelayMs:w,releaseDelayMs:S}});let E=H?.paired_hold_motor;E==="back"||E==="legs"||E==="lumbar"?k.timedMove={deviceId:s,motor:E,...H?.paired_hold_side==="both"?{side:"both"}:{}}:(d==="back"||d==="legs"||d==="lumbar")&&typeof a=="string"&&(k.timedMove={deviceId:s,motor:d,...H?.bed_side==="both"?{side:"both"}:{}})},g=new Map,v=new Map,x=f=>{let d=v.get(f);return d||(d={slot:f},v.set(f,d)),d};for(let f of r){if(f.hidden)continue;let d=f.entity_id,ge=ai(d),z=Ge(f);if(!z)continue;let k=ie(z),H=n.states[d]?.attributes.bed_side??n.states[d]?.attributes.side??k.side;if(e&&H!==e)continue;let a=c&&k.side===H?k.key:z,w;switch(ge){case"cover":{let S=u(a);S.cover=d;let E=n.states[d]?.attributes,at=E?.held_control_up,lt=E?.held_control_down,ct=ze(n,d);ct&&(S.releaseButton=ct);let dt=ye(n,d,f.device_id);if(dt&&(S.holdLease=dt),(E?.held_stop_scope==="motor"||E?.held_stop_scope==="side")&&(S.coverStopScope=E.held_stop_scope),typeof at=="string"&&typeof lt=="string"&&(typeof E?.hold_release_button_key!="string"||S.releaseButton)){(a==="back"||a==="legs"||a==="lumbar")&&(S.timedMove={deviceId:s,motor:a});let ee=E?.hold_start_delay_ms,te=E?.hold_release_delay_ms;(E?.held_stop_scope==="motor"||E?.held_stop_scope==="side")&&f.device_id&&typeof ee=="number"&&Number.isFinite(ee)&&ee>=0&&typeof te=="number"&&Number.isFinite(te)&&te>=0&&(S.deviceId=f.device_id,S.holdEntityId=d,S.heldControls={up:{control:at,startDelayMs:ee,releaseDelayMs:te},down:{control:lt,startDelayMs:ee,releaseDelayMs:te}})}}break;case"sensor":if(a==="eshine_okin_massage"){(t.massage.states??=[]).push(d);break}if(a==="eshine_okin_alarm"){t.utilityStates?.push(d);break}if(a.startsWith("goodvibe_")){t.utilityStates?.push(d);break}if(a==="saved_positions"){t.savedPositions=d;break}if(a.startsWith("doublesleep_")){/^doublesleep_(massage_|sonic_)/.test(a)?(t.massage.states??=[]).push(d):a==="doublesleep_light"?(t.lights.states??=[]).push(d):t.utilityStates?.push(d);break}if(/^adjustamattress_(massage_time|head_intensity|foot_intensity|wave)$/.test(a)){(t.massage.states??=[]).push(d);break}if(a.startsWith("adjustamattress_")){t.utilityStates?.push(d);break}a==="gmmotor_state"||a==="gmmotor_sleep_state"?t.utilityStates?.push(d):a.startsWith("starcode_m1x12_part_")&&a.endsWith("_position")?u(a.slice(0,-9)).position=d:a.endsWith("_angle")?u(a.slice(0,-6)).angle=d:a.startsWith("sleepys_app_position_")||a.startsWith("sleepys_app_field_")?t.utilityStates?.push(d):a.startsWith("reverie_")&&a.endsWith("_massage_intensity")?(t.massage.states??=[]).push(d):a==="sleepys_app_massage_timer_code"||a==="reverie_pairlink_massage_mode"||a==="reverie_pairlink_massage_timer"?(t.massage.states??=[]).push(d):a==="reverie_massage_wave"?(t.massage.states??=[]).push(d):a==="logicdata_air_pump_pressure"?t.firmness.push(d):a==="innova_massage_timer"||a==="glideaway_motion_massage_timer"||a==="bedsense_massage_timer"||a==="app_timer_status"?t.massage.timer=d:a==="bedsense_light_duration"?t.lights.state=d:/^bedsense_(head_bar|wave_bar|head_steps|foot_steps|wave_steps)$/.test(a)?(t.massage.states??=[]).push(d):a.startsWith("starcode_m1x12_light_")?(t.lights.states??=[]).push(d):/^starcode_m1x12_(massage_|sonic_|kneading_)/.test(a)?(t.massage.states??=[]).push(d):a.startsWith("starcode_m1x12_")&&t.utilityStates?.push(d);break;case"number":if(a.startsWith("goodvibe_")){(t.utilityNumbers??=[]).push(d);break}if(a.endsWith("_position_estimated")){u(a.slice(0,-19)).estimate=d;break}if(a.startsWith("adjustamattress_")){(t.utilityNumbers??=[]).push(d);break}a.endsWith("_position")?u(a.slice(0,-9)).position=d:a==="reverie_body_tilt"?u("lumbar").position=d:!e&&k.side&&k.key.endsWith("_position")?u(`${k.key.slice(0,-9)}_${k.side}`).position=d:a.startsWith("massage_")&&a.endsWith("_intensity")||a==="reverie_wave_level"||a==="reverie_massage_wave"||a==="reverie_stk_head_wave"||a==="reverie_stk_global_massage"?t.massage.numbers.push(d):a==="reverie_pairlink_massage_timer"?t.massage.timer=d:a==="bf_cherish_intensity"||a==="bf_cherish_wave"?t.massage.numbers.push(d):a==="light_level"||a==="svane_intensity"||a==="starcode_brightness"||a==="starcode_m1x12_brightness"||a==="vmatbasic_floor_level"||a==="starcode_abm5_4_light_level"?t.lights.level=d:a==="vmatbasic_floor_minutes"?(t.lights.timerMinutes=d,t.lights.timerAppliesImmediately=!0):a==="vibradorm_app_floor_timer_minutes"?t.lights.timerMinutes=d:(w=a.match(/^richmat_mh_(back|foot|pillow)_angle$/))?u(ni[w[1]]).position=d:a==="richmat_mh_light_timer"?t.lights.timer=d:a==="richmat_mh_light_timer_minutes"?(t.lights.timerMinutes=d,t.lights.timerAppliesImmediately=!0):a==="richmat_mh_head_massage_intensity"||a==="richmat_mh_foot_massage_intensity"?t.massage.numbers.push(d):a==="vibradorm_app_mood_speed"||a==="vmatbasic_mood_speed"||a==="vmatbasic_mood_brightness"?i().numbers.push(d):a==="vibradorm_app_massage_speed"||a==="sleeptracker_wave_minutes"?t.massage.numbers.push(d):a==="sleepys_app_color_code"?(t.lights.numbers??=[]).push(d):a.startsWith("sleepys_app_target_axis_")?(t.utilityNumbers??=[]).push(d):/^sleeptracker_(left|right)_level$/.test(a)||a==="fan_level"?t.climate.numbers.push(d):a.startsWith("sleep_number_setting")&&t.firmness.push(d);break;case"button":if(a==="estimate_remote_used"){t.estimateRemote=d;break}if(w=a.match(/^set_(.+)_reference$/)){u(w[1]).reference=d;break}if(a==="doublesleep_massage_action"){t.massage.buttons.push(d);break}if(a==="doublesleep_light_action"){(t.lights.buttons??=[]).push(d);break}if(a==="doublesleep_action"){t.utility.push(d);break}if(a==="adjustamattress_underbed_lighting"){(t.lights.buttons??=[]).push(d);break}if(/^adjustamattress_(head_strength_add|foot_strength_add|wave_add|massage_timer|timer\d+|query_massage.*)$/.test(a)){t.massage.buttons.push(d);break}if(a==="adjustamattress_m1"){g.set(a,d);break}if(a.startsWith("adjustamattress_")){t.utility.push(d);break}We.includes(a)||a.startsWith("preset_")||a.startsWith("sleepys_app_preset_")?(w=a.match(/^preset_memory_(\d+)$/))?x(Number(w[1])).goto=d:g.set(a,d):(w=a.match(/^program_memory_(\d+)$/))?x(Number(w[1])).save=d:(w=a.match(/^sleepys_app_memory_(\d+)$/))?x(Number(w[1])).goto=d:a==="stop"||a==="stop_both"?t.stop=d:a==="connect"?t.connect=d:a==="disconnect"?t.disconnect=d:a==="bedsense_light"?(t.lights.buttons??=[]).push(d):a==="bedsense_massage"?t.massage.buttons.push(d):a==="bedsense_action"?t.utility.push(d):a==="sleeptracker_light_toggle"?t.lights.toggle=d:a==="sleeptracker_light_off"?(t.lights.buttons??=[]).push(d):/^sleeptracker_(massage_|wave_start|wind_down_|local_animation)/.test(a)?t.massage.buttons.push(d):a.startsWith("sleeptracker_")?t.utility.push(d):a.startsWith("sleepys_app_light_")||a.startsWith("sleepys_app_voice_brightness_")||a==="sleepys_app_rgb_action"?(t.lights.buttons??=[]).push(d):a.startsWith("sleepys_app_massage_")?t.massage.buttons.push(d):a==="toggle_light"?t.lights.toggle=d:a==="light_cycle"||a==="starcode_light_cycle"?t.lights.cycle=d:a==="vibradorm_app_mood_toggle"||a==="vmatbasic_mood_toggle"?i().toggle=d:a==="vmatbasic_mood_nightlight"?(i().buttons??=[]).push(d):a==="vmatbasic_floor_toggle"||a==="vmatbasic_floor_hold"?t.lights.toggle=d:a.startsWith("vmatbasic_massage_")?t.massage.buttons.push(d):a==="vibradorm_app_floor_timer_toggle"?t.lights.timerToggle=d:a==="remacro_led_brightness_save"?(t.lights.buttons??=[]).push(d):a==="starcode_abm5_4_light_plus"||a==="starcode_abm5_4_light_minus"||a==="starcode_abm5_4_light_on"||a==="starcode_abm5_4_light_off"?(t.lights.buttons??=[]).push(d):a==="starcode_abm5_4_massage_release"?t.massage.buttons.push(d):a.startsWith("starcode_abm5_4_")?t.utility.push(d):a==="okin_app_home"||a.startsWith("simmons_inclined")?g.set(a,d):a==="simmons_sync_clock"||a==="simmons_refresh_alarms"||a==="glideaway_motion_query_alarm"||a==="bf_query_alarm"?t.utility.push(d):a.startsWith("eshine_okin_massage_")?t.massage.buttons.push(d):a.startsWith("eshine_okin_")?t.utility.push(d):a.startsWith("eshine_massage_")?t.massage.buttons.push(d):a.startsWith("eshine_save_")?t.utility.push(d):a==="richmat_mh_massage"?t.massage.buttons.push(d):a==="richmat_mh_preset"?g.set(`${a}:${d}`,d):a==="hjbed_action"||a==="goodvibe_action"||a.startsWith("richmat_mh_")?t.utility.push(d):a.startsWith("adjustable_lumbar_wave_")||a==="adjustable_lumbar_massage_on"?t.massage.buttons.push(d):a.startsWith("adjustable_lumbar_")?t.utility.push(d):a==="logicdata_app_query_massage"?t.massage.buttons.push(d):a.startsWith("logicdata_air_pump_")?t.utility.push(d):/^comfort_enhancements_(head|foot|timer)_cycle$/.test(a)||a==="ore_comfort_massage_start"||a==="innova_massage_level"||a==="innova_massage_timer_hold"?t.massage.buttons.push(d):a==="ore_comfort_program_flat"||a==="ore_comfort_program_zero_g"?t.utility.push(d):a==="isleep_pattern"||a==="coolbase_head_massage"||a==="coolbase_foot_massage"||a==="coolbase_massage_mode"?t.massage.buttons.push(d):a==="comfort_enhancements_quiet_sleep"?g.set(a,d):a==="restonic_zzz"||a.startsWith("coolbase_")?t.utility.push(d):a==="vibradorm_app_massage_automatic"||a==="vibradorm_app_massage_individual"||a.startsWith("starcode_m1x12_hold_")?t.massage.buttons.push(d):(w=a.match(/^(starcode_m1x12_part_\d+)_(up|down)$/))?m(d,w[1],w[2],f.device_id):a==="sync_positions"||a==="child_lock_toggle"||a==="auxiliary_action"||a==="remote_action"||a==="solace_music_toggle"||a==="solace_music_off"||a==="wake_controller"||a==="octo_all_down"||a==="reset_defaults"||a==="factory_reset"||a==="isleep_all_up"||a==="isleep_all_down"||a==="vibradorm_app_all_up"||a==="vibradorm_app_all_down"||a==="vibradorm_app_sync"||a==="vibradorm_app_refresh_info"||a==="vmatbasic_all_up"||a==="vmatbasic_all_down"||a==="vmatbasic_refresh_info"||a.startsWith("starcode_save_")||a==="starcode_reset"||a==="starcode_query"||a==="starcode_light_mode"||a.startsWith("starcode_m1x12_")?t.utility.push(d):a.startsWith("massage_")?t.massage.buttons.push(d):a.startsWith("sleepys_app_")||a==="casper_base_action"?t.utility.push(d):a==="bf_cherish_both_up"||a==="bf_cherish_both_down"?m(d,"back_legs",a.endsWith("_up")?"up":"down",f.device_id):(w=a.match(/^(.+)_(up|down)$/))&&m(d,w[1],w[2],f.device_id);break;case"switch":a==="under_bed_lights"?t.lights.switch=d:a==="synchro_mode"?t.synchro=d:(a==="linak_automatic_drive"||a==="automatic_light"||a==="remote_control_lock")&&t.utility.push(d);break;case"light":t.lights.light=d;break;case"binary_sensor":if(a.startsWith("doublesleep_")){t.utilityStates?.push(d);break}if(a.startsWith("adjustamattress_")){t.utilityStates?.push(d);break}a==="ble_connection"?t.connectivity=d:a==="memory_save_response_observed"?t.utilityStates?.push(d):a==="sleeptracker_wind_down_running"?(t.massage.states??=[]).push(d):a==="reverie_pairlink_low_battery"?t.utility.push(d):a==="under_bed_lights"||a==="adjustable_lite_light"||a==="innova_light"||a==="sleeptracker_light_on"||a==="starcode_m1x12_light_on"?t.lights.state=d:/^starcode_m1x12_(massage_|sonic_|kneading_)/.test(a)?(t.massage.states??=[]).push(d):a.startsWith("starcode_m1x12_")?t.utilityStates?.push(d):a.startsWith("bed_presence")&&t.presence.push(d);break;case"select":if(a==="doublesleep_child_lock"){(t.utilitySelects??=[]).push(d);break}if(/^adjustamattress_(head|foot|wave)_selector$/.test(a)){(t.massage.selects??=[]).push(d);break}if(a.startsWith("adjustamattress_")){(t.utilitySelects??=[]).push(d);break}a==="goodvibe_massage_timer"||a==="goodvibe_light_duration"||a==="hjbed_layout"||a==="motion_bed_active_module"||a.startsWith("okin_app_")?(t.utilitySelects??=[]).push(d):a==="reverie_stk_side"?(t.utilitySelects??=[]).push(d):a==="sleepys_app_massage_timer_code"||a==="reverie_pairlink_massage_mode"||a==="reverie_pairlink_massage_rhythm"?(t.massage.selects??=[]).push(d):a==="light_timer"?t.lights.timer=d:a==="remacro_control_side"||a==="goodvibe_side"?t.controlSide=d:a==="starcode_color"||a==="vibradorm_app_mood_palette"||a==="vibradorm_app_mood_effect"||a==="vmatbasic_mood_palette"||a==="vmatbasic_mood_effect"?i().selects.push(d):a==="sleeptracker_wave_frequency"||/^sleeptracker_massage_(head_level|foot_level|pattern_option)$/.test(a)?(t.massage.selects??=[]).push(d):/^sleeptracker_(left|right)_(mode|curve)$/.test(a)?t.climate.selects.push(d):a==="vibradorm_app_massage_wave"?(t.massage.selects??=[]).push(d):a==="richmat_mh_motor_mode"||a==="richmat_mh_snore"?(t.utilitySelects??=[]).push(d):a.startsWith("richmat_mh_waist_")?(t.massage.selects??=[]).push(d):a==="massage_timer"||a==="starcode_abm5_4_massage_timer"||a==="ore_comfort_massage_timer"?t.massage.timer=d:/thermal|footwarming|foundation/.test(a)&&t.climate.selects.push(d);break;case"climate":t.climate.entities.push(d);break}}let y=[...l.keys()],$=[...yt.filter(f=>l.has(f)),...y.filter(f=>!yt.includes(f)).sort()];t.motors=$.map(f=>l.get(f)).filter(f=>f.cover||f.up||f.down||f.angle||f.position);let b=[...g.keys()];return t.presets=[...We.filter(f=>g.has(f)),...b.filter(f=>!We.includes(f)).sort()].map(f=>g.get(f)),t.memory=[...v.values()].filter(f=>f.goto||f.save).sort((f,d)=>f.slot-d.slot),t}function we(n,s){return!s||!n?.entities?!1:Object.values(n.entities).some(e=>e.device_id===s&&e.platform===D&&(n.states[e.entity_id]?.attributes.bed_side==="both"||ie(Ge(e)).side==="both"))}function se(n,s){if(!s||!n?.devices)return[];let e=i=>(L(n,i)??i).toLowerCase(),t=i=>{for(let o of Object.values(n.entities??{})){if(o.device_id!==i||o.platform!=="adjustable_bed")continue;let r=n.states[o.entity_id]?.attributes.bed_side??ie(Ge(o)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(n.devices).filter(i=>(i.parent_device_id??i.via_device_id)===s).map(i=>i.id).sort((i,o)=>t(i)-t(o)||e(i).localeCompare(e(o)))}function $e(n,s){if(!s||!n?.devices)return s;let e=n.devices[s]?.parent_device_id??n.devices[s]?.via_device_id;return e&&n.devices[e]&&se(n,e).length?e:s}function j(n){let s=n.lights;return n.motors.length===0&&!n.synchro&&!n.controlSide&&n.firmness.length===0&&n.presets.length===0&&n.memory.length===0&&!n.stop&&!n.connect&&!n.disconnect&&!n.connectivity&&!V(s)&&!s.state&&n.massage.buttons.length===0&&n.massage.numbers.length===0&&!n.massage.selects?.length&&!n.massage.states?.length&&!n.massage.timer&&n.climate.entities.length===0&&n.climate.selects.length===0&&n.climate.numbers.length===0&&n.utility.length===0&&!n.utilityNumbers?.length&&!n.utilitySelects?.length&&!n.utilityStates?.length&&!n.savedPositions}function V(n){return!!(n.light||n.switch||n.level||n.toggle||n.numbers?.length||n.buttons?.length||n.states?.length||n.cycle||n.timer||n.timerMinutes||n.timerToggle||n.mood?.toggle||n.mood?.selects.length||n.mood?.numbers.length||n.mood?.buttons?.length)}var Ie="adjustable-bed-card",xt={type:Ie,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(n,s)=>{let e=n.entities[s];return e?.platform!==D||!e.device_id?null:{config:{type:`custom:${Ie}`,device_id:e.device_id}}}};function ci(n){let s=n.customCards??=[],e=s.findIndex(t=>t.type===Ie);e===-1?s.push(xt):s[e]=xt}function ke(n,s,e=window){let t=e.customElements;t.get(n)||t.define(n,s),t.whenDefined("home-assistant").then(()=>{let i=e.customElements;i!==t&&!i.get(n)&&i.define(n,s)})}typeof window<"u"&&ci(window);var Ee=globalThis,Se=Ee.ShadowRoot&&(Ee.ShadyCSS===void 0||Ee.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Ue=Symbol(),wt=new WeakMap,oe=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==Ue)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(Se&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=wt.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&wt.set(e,s))}return s}toString(){return this.cssText}},$t=n=>new oe(typeof n=="string"?n:n+"",void 0,Ue),ne=(n,...s)=>{let e=n.length===1?n[0]:s.reduce((t,i,o)=>t+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[o+1],n[0]);return new oe(e,n,Ue)},kt=(n,s)=>{if(Se)n.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=Ee.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,n.appendChild(t)}},qe=Se?n=>n:n=>n instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return $t(e)})(n):n;var{is:di,defineProperty:pi,getOwnPropertyDescriptor:hi,getOwnPropertyNames:ui,getOwnPropertySymbols:mi,getPrototypeOf:gi}=Object,Te=globalThis,Et=Te.trustedTypes,_i=Et?Et.emptyScript:"",fi=Te.reactiveElementPolyfillSupport,re=(n,s)=>n,ae={toAttribute(n,s){switch(s){case Boolean:n=n?_i:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,s){let e=n;switch(s){case Boolean:e=n!==null;break;case Number:e=n===null?null:Number(n);break;case Object:case Array:try{e=JSON.parse(n)}catch{e=null}}return e}},Me=(n,s)=>!di(n,s),St={attribute:!0,type:String,converter:ae,reflect:!1,useDefault:!1,hasChanged:Me};Symbol.metadata??=Symbol("metadata"),Te.litPropertyMetadata??=new WeakMap;var B=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=St){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&pi(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:o}=hi(this.prototype,s)??{get(){return this[e]},set(r){this[e]=r}};return{get:i,set(r){let c=i?.call(this);o?.call(this,r),this.requestUpdate(s,c,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??St}static _$Ei(){if(this.hasOwnProperty(re("elementProperties")))return;let s=gi(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(re("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(re("properties"))){let e=this.properties,t=[...ui(e),...mi(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(qe(i))}else s!==void 0&&e.push(qe(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return kt(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let o=(t.converter?.toAttribute!==void 0?t.converter:ae).toAttribute(e,t.type);this._$Em=s,o==null?this.removeAttribute(i):this.setAttribute(i,o),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let o=t.getPropertyOptions(i),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:ae;this._$Em=i;let c=r.fromAttribute(e,o.type);this[i]=c??this._$Ej?.get(i)??c,this._$Em=null}}requestUpdate(s,e,t,i=!1,o){if(s!==void 0){let r=this.constructor;if(i===!1&&(o=this[s]),t??=r.getPropertyOptions(s),!((t.hasChanged??Me)(o,e)||t.useDefault&&t.reflect&&o===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:o},r){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??e??this[s]),o!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,o]of this._$Ep)this[i]=o;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,o]of t){let{wrapped:r}=o,c=this[i];r!==!0||this._$AL.has(i)||c===void 0||this.C(i,void 0,o,c)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};B.elementStyles=[],B.shadowRootOptions={mode:"open"},B[re("elementProperties")]=new Map,B[re("finalized")]=new Map,fi?.({ReactiveElement:B}),(Te.reactiveElementVersions??=[]).push("2.1.2");var et=globalThis,Tt=n=>n,Ce=et.trustedTypes,Mt=Ce?Ce.createPolicy("lit-html",{createHTML:n=>n}):void 0,Bt="$lit$",O=`lit$${Math.random().toFixed(9).slice(2)}$`,Lt="?"+O,vi=`<${Lt}>`,K=document,ce=()=>K.createComment(""),de=n=>n===null||typeof n!="object"&&typeof n!="function",tt=Array.isArray,bi=n=>tt(n)||typeof n?.[Symbol.iterator]=="function",Ve=`[ \t
\f\r]`,le=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Ct=/-->/g,At=/>/g,N=RegExp(`>|${Ve}(?:([^\\s"'>=/]+)(${Ve}*=${Ve}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),Rt=/'/g,Pt=/"/g,Dt=/^(?:script|style|textarea|title)$/i,it=n=>(s,...e)=>({_$litType$:n,strings:s,values:e}),h=it(1),Ae=it(2),Gi=it(3),W=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),Ht=new WeakMap,F=K.createTreeWalker(K,129);function jt(n,s){if(!tt(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Mt!==void 0?Mt.createHTML(s):s}var yi=(n,s)=>{let e=n.length-1,t=[],i,o=s===2?"<svg>":s===3?"<math>":"",r=le;for(let c=0;c<e;c++){let l=n[c],u,m,g=-1,v=0;for(;v<l.length&&(r.lastIndex=v,m=r.exec(l),m!==null);)v=r.lastIndex,r===le?m[1]==="!--"?r=Ct:m[1]!==void 0?r=At:m[2]!==void 0?(Dt.test(m[2])&&(i=RegExp("</"+m[2],"g")),r=N):m[3]!==void 0&&(r=N):r===N?m[0]===">"?(r=i??le,g=-1):m[1]===void 0?g=-2:(g=r.lastIndex-m[2].length,u=m[1],r=m[3]===void 0?N:m[3]==='"'?Pt:Rt):r===Pt||r===Rt?r=N:r===Ct||r===At?r=le:(r=N,i=void 0);let x=r===N&&n[c+1].startsWith("/>")?" ":"";o+=r===le?l+vi:g>=0?(t.push(u),l.slice(0,g)+Bt+l.slice(g)+O+x):l+O+(g===-2?c:x)}return[jt(n,o+(n[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},pe=class n{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let o=0,r=0,c=s.length-1,l=this.parts,[u,m]=yi(s,e);if(this.el=n.createElement(u,t),F.currentNode=this.el.content,e===2||e===3){let g=this.el.content.firstChild;g.replaceWith(...g.childNodes)}for(;(i=F.nextNode())!==null&&l.length<c;){if(i.nodeType===1){if(i.hasAttributes())for(let g of i.getAttributeNames())if(g.endsWith(Bt)){let v=m[r++],x=i.getAttribute(g).split(O),y=/([.?@])?(.*)/.exec(v);l.push({type:1,index:o,name:y[2],strings:x,ctor:y[1]==="."?Je:y[1]==="?"?Qe:y[1]==="@"?Xe:J}),i.removeAttribute(g)}else g.startsWith(O)&&(l.push({type:6,index:o}),i.removeAttribute(g));if(Dt.test(i.tagName)){let g=i.textContent.split(O),v=g.length-1;if(v>0){i.textContent=Ce?Ce.emptyScript:"";for(let x=0;x<v;x++)i.append(g[x],ce()),F.nextNode(),l.push({type:2,index:++o});i.append(g[v],ce())}}}else if(i.nodeType===8)if(i.data===Lt)l.push({type:2,index:o});else{let g=-1;for(;(g=i.data.indexOf(O,g+1))!==-1;)l.push({type:7,index:o}),g+=O.length-1}o++}}static createElement(s,e){let t=K.createElement("template");return t.innerHTML=s,t}};function Y(n,s,e=n,t){if(s===W)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,o=de(s)?void 0:s._$litDirective$;return i?.constructor!==o&&(i?._$AO?.(!1),o===void 0?i=void 0:(i=new o(n),i._$AT(n,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=Y(n,i._$AS(n,s.values),i,t)),s}var Ye=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??K).importNode(e,!0);F.currentNode=i;let o=F.nextNode(),r=0,c=0,l=t[0];for(;l!==void 0;){if(r===l.index){let u;l.type===2?u=new he(o,o.nextSibling,this,s):l.type===1?u=new l.ctor(o,l.name,l.strings,this,s):l.type===6&&(u=new Ze(o,this,s)),this._$AV.push(u),l=t[++c]}r!==l?.index&&(o=F.nextNode(),r++)}return F.currentNode=K,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},he=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=Y(this,s,e),de(s)?s===p||s==null||s===""?(this._$AH!==p&&this._$AR(),this._$AH=p):s!==this._$AH&&s!==W&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):bi(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==p&&de(this._$AH)?this._$AA.nextSibling.data=s:this.T(K.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=pe.createElement(jt(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let o=new Ye(i,this),r=o.u(this.options);o.p(e),this.T(r),this._$AH=o}}_$AC(s){let e=Ht.get(s.strings);return e===void 0&&Ht.set(s.strings,e=new pe(s)),e}k(s){tt(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let o of s)i===e.length?e.push(t=new n(this.O(ce()),this.O(ce()),this,this.options)):t=e[i],t._$AI(o),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=Tt(s).nextSibling;Tt(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},J=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,o){this.type=1,this._$AH=p,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=o,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=p}_$AI(s,e=this,t,i){let o=this.strings,r=!1;if(o===void 0)s=Y(this,s,e,0),r=!de(s)||s!==this._$AH&&s!==W,r&&(this._$AH=s);else{let c=s,l,u;for(s=o[0],l=0;l<o.length-1;l++)u=Y(this,c[t+l],e,l),u===W&&(u=this._$AH[l]),r||=!de(u)||u!==this._$AH[l],u===p?s=p:s!==p&&(s+=(u??"")+o[l+1]),this._$AH[l]=u}r&&!i&&this.j(s)}j(s){s===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},Je=class extends J{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===p?void 0:s}},Qe=class extends J{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==p)}},Xe=class extends J{constructor(s,e,t,i,o){super(s,e,t,i,o),this.type=5}_$AI(s,e=this){if((s=Y(this,s,e,0)??p)===W)return;let t=this._$AH,i=s===p&&t!==p||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,o=s!==p&&(t===p||i);i&&this.element.removeEventListener(this.name,this,t),o&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},Ze=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){Y(this,s)}};var xi=et.litHtmlPolyfillSupport;xi?.(pe,he),(et.litHtmlVersions??=[]).push("3.3.3");var Ot=(n,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let o=e?.renderBefore??null;t._$litPart$=i=new he(s.insertBefore(ce(),o),o,void 0,e??{})}return i._$AI(n),i};var st=globalThis,P=class extends B{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=Ot(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return W}};P._$litElement$=!0,P.finalized=!0,st.litElementHydrateSupport?.({LitElement:P});var wi=st.litElementPolyfillSupport;wi?.({LitElement:P});(st.litElementVersions??=[]).push("4.2.2");var $i={attribute:!0,type:String,converter:ae,reflect:!1,hasChanged:Me},ki=(n=$i,s,e)=>{let{kind:t,metadata:i}=e,o=globalThis.litPropertyMetadata.get(i);if(o===void 0&&globalThis.litPropertyMetadata.set(i,o=new Map),t==="setter"&&((n=Object.create(n)).wrapped=!0),o.set(e.name,n),t==="accessor"){let{name:r}=e;return{set(c){let l=s.get.call(this);s.set.call(this,c),this.requestUpdate(r,l,n,!0,c)},init(c){return c!==void 0&&this.C(r,void 0,n,c),c}}}if(t==="setter"){let{name:r}=e;return function(c){let l=this[r];s.call(this,c),this.requestUpdate(r,l,n,!0,c)}}throw Error("Unsupported decorator location: "+t)};function Q(n){return(s,e)=>typeof e=="object"?ki(n,s,e):((t,i,o)=>{let r=i.hasOwnProperty(o);return i.constructor.createProperty(o,t),r?Object.getOwnPropertyDescriptor(i,o):void 0})(n,s,e)}function R(n){return Q({...n,state:!0,attribute:!1})}var G=n=>Math.max(0,Math.min(75,n));function ot(n,s="theme"){let e=G(n.upper.angle??0),t=G(n.lower.angle??0),i=`rotate(${e} 150 70)`,o=`rotate(${-t} 150 70)`,r=c=>{if(c.angle===void 0)return"";let l=`${n.estimated?"\u2248 ":""}${Math.round(G(c.angle))}\xB0`;return`${c.label?`${c.label} `:""}${l}`};return Ae`
    <svg
      class="bed-graphic bed-graphic-${s} ${n.moving?"is-moving":""} ${n.estimated?"is-estimated":""}"
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
  `}function nt(n){let s=G(n.left.upper.angle??0),e=G(n.left.lower.angle??0),t=G(n.right.upper.angle??0),i=G(n.right.lower.angle??0),o=(r,c,l,u,m=!1)=>Ae`
    <g
      class="dual-bed-side dual-bed-side-${r} ${u?"is-moving":""} ${m?"is-estimated":""}"
      fill=${`url(#abDual${r==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${`rotate(${-l} 150 70)`}
      >
        <rect class="dual-bed-surface" x="150" y="58" width="108" height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${`rotate(${c} 150 70)`}
      >
        <rect class="dual-bed-surface" x="42" y="58" width="108" height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
    </g>
  `;return Ae`
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
      ${o("right",t,i,n.right.moving,n.right.estimated)}
      ${o("left",s,e,n.left.moving,n.left.estimated)}
    </svg>
  `}function ue(n){let s=n.find(t=>t.key==="back"||t.key==="head"),e=n.find(t=>t.key==="legs"||t.key==="feet");return s&&e?{upper:s,lower:e}:void 0}function zt(n,s){let e=n.motors.filter(i=>{let o=i.angle??i.position;return s.states[o??""]?.attributes.unit_of_measurement==="\xB0"}),t=n.motors.filter(i=>typeof s.states[i.estimate??""]?.attributes.max_angle=="number");return ue(e)!==void 0||ue(t)!==void 0}var Nt={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","tap.moving_up":"Moving up \xB7 tap to stop","tap.moving_down":"Moving down \xB7 tap to stop","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.motors_group":"Motors","editor.tap_to_move":"Tap to start and stop movement","editor.tap_to_move_hint":"Tap an arrow to start. Tap any arrow or Stop to end. Movement stops by itself after at most 30 seconds.","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both","section.saved_positions":"Saved positions","editor.show_saved_positions":"Saved positions","estimate.readout":"\u2248 {percent}%","estimate.readout_was":"Was \u2248 {percent}%","estimate.unknown":"Unknown","estimate.not_calibrated":"Not calibrated","estimate.chip_estimated":"Estimated","estimate.chip_unconfirmed":"Unconfirmed","estimate.chip_unknown":"Unknown","estimate.alert_calibrate":"Estimated positions are on but not calibrated yet.","estimate.calibrate_now":"Calibrate now","estimate.alert_unconfirmed":"Position unconfirmed after restart. Last estimate: {values}. Saved positions are paused until you confirm.","estimate.alert_unknown":"Position unknown: {reason}. Saved positions are paused until you set the reference.","estimate.reason_not_referenced":"no reference is set yet","estimate.reason_restart":"Home Assistant restarted","estimate.reason_failed_move":"a movement failed","estimate.reason_untracked_move":"the bed moved in a way that is not timed","estimate.reason_hardware_preset":"a hardware preset or memory moved the bed","estimate.reason_remote":"you reported using the remote","estimate.reason_connection_lost":"the connection dropped during a movement","estimate.unchanged":"It hasn't moved","estimate.set_reference":"Set reference\u2026","estimate.edit":"Edit","estimate.done":"Done","estimate.edit_hint":"Tap a position to rename, update or delete it.","estimate.save":"Save\u2026","estimate.footer":"Estimated from movement time. Remote use is not seen.","estimate.scope_both":"Both sides","estimate.scope_left":"Left only","estimate.scope_right":"Right only","estimate.recalled":"Moved to {name} (estimated)","estimate.ref_title":"Set reference","estimate.ref_text":"Choose how to get a known position. The bed never moves on its own to recover.","estimate.ref_lowering":"The lowering has finished. Check that the bed is completely flat, then confirm.","estimate.ref_flat":"The bed is flat now","estimate.ref_flat_detail":"{motors} are fully down. Sets them to 0%.","estimate.ref_lower":"Lower to flat, then I confirm","estimate.ref_lower_detail":"Moves down for the full travel time plus a margin. You confirm it is flat afterwards.","estimate.ref_only":"Only the {motor}","estimate.ref_only_detail":"The other motors keep their estimate.","estimate.ref_lower_start":"Lower","estimate.ref_confirm":"Confirm flat","estimate.save_title":"Save current position","estimate.name":"Name","estimate.create_button":"Also create a button entity","estimate.create_button_detail":"For automations and voice.","estimate.save_note":"Recall moves each motor for the calculated time. Expect a few percent difference.","estimate.save_confirm":"Save","estimate.edit_title":'Edit "{name}"',"estimate.saved":"Saved","estimate.now":"Now","estimate.update_blocked":'"Update to current" needs every side it covers confirmed. Set a reference first.',"estimate.delete":"Delete","estimate.update":"Update to current","estimate.ref_lowering_running":"The bed is lowering past its full travel time. Wait until it has stopped, or press Stop."};var Ft={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","tap.moving_up":"Beveger seg opp \xB7 trykk for \xE5 stoppe","tap.moving_down":"Beveger seg ned \xB7 trykk for \xE5 stoppe","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.motors_group":"Motorer","editor.tap_to_move":"Trykk for \xE5 starte og stoppe bevegelse","editor.tap_to_move_hint":"Trykk p\xE5 en pil for \xE5 starte. Trykk p\xE5 en pil eller Stopp for \xE5 avslutte. Bevegelsen stopper av seg selv etter maks 30 sekunder.","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge","section.saved_positions":"Lagrede posisjoner","editor.show_saved_positions":"Lagrede posisjoner","estimate.readout":"\u2248 {percent} %","estimate.readout_was":"Var \u2248 {percent} %","estimate.unknown":"Ukjent","estimate.not_calibrated":"Ikke kalibrert","estimate.chip_estimated":"Ansl\xE5tt","estimate.chip_unconfirmed":"Ubekreftet","estimate.chip_unknown":"Ukjent","estimate.alert_calibrate":"Ansl\xE5tte posisjoner er sl\xE5tt p\xE5, men ikke kalibrert enn\xE5.","estimate.calibrate_now":"Kalibrer n\xE5","estimate.alert_unconfirmed":"Posisjonen er ubekreftet etter omstart. Siste anslag: {values}. Lagrede posisjoner er satt p\xE5 pause til du bekrefter.","estimate.alert_unknown":"Posisjonen er ukjent: {reason}. Lagrede posisjoner er satt p\xE5 pause til du setter referansen.","estimate.reason_not_referenced":"ingen referanse er satt enn\xE5","estimate.reason_restart":"Home Assistant startet p\xE5 nytt","estimate.reason_failed_move":"en bevegelse mislyktes","estimate.reason_untracked_move":"sengen beveget seg uten tidtaking","estimate.reason_hardware_preset":"en forh\xE5ndsinnstilling eller et minne i sengen flyttet den","estimate.reason_remote":"du meldte at fjernkontrollen ble brukt","estimate.reason_connection_lost":"forbindelsen falt ut under en bevegelse","estimate.unchanged":"Den har ikke flyttet seg","estimate.set_reference":"Sett referanse\u2026","estimate.edit":"Rediger","estimate.done":"Ferdig","estimate.edit_hint":"Trykk p\xE5 en posisjon for \xE5 gi den nytt navn, oppdatere eller slette den.","estimate.save":"Lagre\u2026","estimate.footer":"Ansl\xE5tt fra bevegelsestid. Bruk av fjernkontrollen registreres ikke.","estimate.scope_both":"Begge sider","estimate.scope_left":"Bare venstre","estimate.scope_right":"Bare h\xF8yre","estimate.recalled":"Flyttet til {name} (ansl\xE5tt)","estimate.ref_title":"Sett referanse","estimate.ref_text":"Velg hvordan du f\xE5r en kjent posisjon. Sengen flytter seg aldri av seg selv for \xE5 finne den igjen.","estimate.ref_lowering":"Senkingen er ferdig. Sjekk at sengen ligger helt flatt, og bekreft.","estimate.ref_flat":"Sengen er flat n\xE5","estimate.ref_flat_detail":"{motors} er helt nede. Setter dem til 0 %.","estimate.ref_lower":"Senk til flat, s\xE5 bekrefter jeg","estimate.ref_lower_detail":"Senker i hele bevegelsestiden pluss en margin. Du bekrefter etterp\xE5 at den er flat.","estimate.ref_only":"Bare {motor}","estimate.ref_only_detail":"De andre motorene beholder anslaget sitt.","estimate.ref_lower_start":"Senk","estimate.ref_confirm":"Bekreft flat","estimate.save_title":"Lagre n\xE5v\xE6rende posisjon","estimate.name":"Navn","estimate.create_button":"Lag ogs\xE5 en knappeentitet","estimate.create_button_detail":"For automasjoner og tale.","estimate.save_note":"Henting flytter hver motor i den beregnede tiden. Regn med noen prosent avvik.","estimate.save_confirm":"Lagre","estimate.edit_title":"Rediger \xAB{name}\xBB","estimate.saved":"Lagret","estimate.now":"N\xE5","estimate.update_blocked":"\xABOppdater til n\xE5v\xE6rende\xBB krever at alle sidene den dekker er bekreftet. Sett en referanse f\xF8rst.","estimate.delete":"Slett","estimate.update":"Oppdater til n\xE5v\xE6rende","estimate.ref_lowering_running":"Sengen senkes lenger enn hele bevegelsestiden. Vent til den har stoppet, eller trykk Stopp."};var I={en:Nt,nb:Ft};function Ti(n){let s=(n?.locale?.language||n?.language||"en").toLowerCase(),e=s.split("-")[0];return I[s]?I[s]:I[e]?I[e]:e==="nn"||e==="no"?I.nb:I.en}function _(n,s,e){let i=Ti(n)[s]??I.en[s]??s;if(e)for(let[o,r]of Object.entries(e))i=i.replace(`{${o}}`,r);return i}var Kt=["glance","quick","controls"];function Wt(n,s){let e={...n,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:s==="glance"?"names":"angles",show_side_selector:!0,show_motors:s==="controls",show_lighting:!1,show_connection:!1,animate:!0};return s==="glance"?e.compact_actions=[]:delete e.compact_actions,e}function rt(n,s){return[...s.presets,...s.memory.flatMap(e=>e.goto?[e.goto]:[])].flatMap(e=>{let t=n.entities[e]?.translation_key;return t?[{key:ie(t).key,entityId:e}]:[]})}function Pe(n,s,e){let t=rt(n,s);if(e){let r=new Map(t.map(c=>[c.key,c]));return[...new Set(e)].flatMap(c=>{let l=r.get(c);return l?[l]:[]})}let i=t.find(r=>r.key==="preset_flat"),o=t.find(r=>r.key.startsWith("preset_memory_"))??t.find(r=>r!==i);return[i,o].filter(r=>r!==void 0)}function He(n){return n.stop?[n.stop]:n.motors.flatMap(s=>s.cover?[s.cover]:[])}function Be(n){if(!(!n||!n.startsWith("/")||/^\/[/\\]/.test(n)||/[\\\s]/.test(n)))return n}function Le(n,s){let e=$e(n,s),t=se(n,e);return e&&t.length?[{key:"both",label:_(n,"card.both_sides"),bed:A(n,e)},...t.map(i=>({key:i,label:L(n,i)??i,bed:A(n,i)}))]:we(n,s)?["both","left","right"].map(i=>({key:i,label:_(n,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:A(n,s,i)})):[{key:"both",label:_(n,"card.both_sides"),bed:A(n,s)}]}var Gt=n=>typeof n=="number"&&Number.isFinite(n)?n:void 0;function De(n,s){let e=s.estimate,t=e?n?.states[e]:void 0;if(!e||!t)return;let i=t.attributes,o=typeof i.bed_side=="string"?i.bed_side:void 0;if(t.state==="unavailable")return{motor:s.key,entityId:e,state:"not_calibrated",side:o};let r=i.estimate_state,c=r==="tracking"||r==="unconfirmed"||r==="unknown"?r:"unknown",l=Number.parseFloat(t.state);return{motor:s.key,entityId:e,state:c,percent:c==="tracking"&&Number.isFinite(l)?l:Gt(i.last_estimate),reason:typeof i.estimate_reason=="string"?i.estimate_reason:void 0,maxAngle:Gt(i.max_angle),side:o}}function me(n,s){return s.flatMap(e=>{let t=De(n,e);return t?[t]:[]})}function X(n,s){let e=n.percent===void 0?void 0:`${Math.round(n.percent)}`;return n.state==="tracking"&&e!==void 0?s("estimate.readout",{percent:e}):n.state==="unconfirmed"&&e!==void 0?s("estimate.readout_was",{percent:e}):n.state==="not_calibrated"?s("estimate.not_calibrated"):s("estimate.unknown")}function It(n){if(n.length!==0)return n.some(s=>s.state==="unknown"||s.state==="not_calibrated")?"unknown":n.some(s=>s.state==="unconfirmed")?"unconfirmed":"estimated"}function Ut(n){if(n.some(t=>t.state==="not_calibrated"))return{kind:"calibrate"};let s=n.filter(t=>t.state==="unknown");if(s.length)return{kind:"unknown",reason:s[0].reason};let e=n.filter(t=>t.state==="unconfirmed");if(e.length)return{kind:"unconfirmed",estimates:e}}function qt(n,s){let e=s?n?.states[s]?.attributes.positions:void 0;return Array.isArray(e)?e.flatMap(t=>{if(!t||typeof t!="object")return[];let{id:i,name:o,button:r,beds:c}=t;return typeof i!="string"||typeof o!="string"||!c||typeof c!="object"?[]:[{id:i,name:o,button:r!==!1,beds:c}]}):[]}function Vt(n,s){return n.filter(e=>{let t=Object.keys(e.beds);return t.length>0&&t.every(i=>s.includes(i))})}function Yt(n){let s=Object.keys(n.beds);return s.includes("left")&&s.includes("right")?"both":s.includes("left")?"left":s.includes("right")?"right":"bed"}function Jt(n,s){let e=Object.entries(n.beds);return e.length>0&&e.every(([t,i])=>{let o=s[t]??[],r=Object.keys(i);return r.length>0&&r.every(c=>o.find(l=>l.motor===c)?.state==="tracking")})}function je(n){return n.length>0&&n.every(s=>s.state==="tracking")}function Qt(n){if(!(!n||n.state!=="tracking")&&!(n.percent===void 0||n.maxAngle===void 0))return n.percent/100*n.maxAngle}var Xt="4.3.0";function Zt(n,s){return{graphic:zt(n,s),motors:n.motors.some(e=>e.cover||e.up||e.down)||!!n.stop||!!n.synchro,firmness:n.firmness.length>0,presets:n.presets.length>0,saved_positions:!!n.savedPositions,memory:n.memory.length>0,lighting:V(n.lights)||!!n.lights.state,massage:n.massage.buttons.length>0||n.massage.numbers.length>0||!!n.massage.states?.length||!!n.massage.selects?.length||!!n.massage.timer,utility:n.utility.length>0,climate:n.climate.entities.length>0||n.climate.selects.length>0||n.climate.numbers.length>0,connection:!!(n.connect||n.disconnect)}}var Mi="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",Ci="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",Ai=(n,s)=>n.length===s.length&&n.every((e,t)=>e===s[t]),Z=class extends P{constructor(){super(...arguments);this._computeLabel=e=>_(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!this.hass||!e)return;let t=Le(this.hass,e).map(r=>r.bed),i=t[0];if(!i)return;let o=new Map;for(let r of t)for(let c of r.memory){let l=o.get(c.slot);o.set(c.slot,{slot:c.slot,goto:l?.goto??c.goto,save:l?.save??c.save})}return{...i,memory:[...o.values()].sort((r,c)=>r.slot-c.slot)}}_presentKeys(e){let t=this.hass?Le(this.hass,this._config?.device_id).map(i=>i.bed):[e];return q.filter(i=>t.some(o=>Zt(o,this.hass)[i]))}_orderedKeys(e){let t=this._presentKeys(e),o=(this._config?.section_order??[]).filter(c=>t.includes(c)),r=t.filter(c=>!o.includes(c));return[...o,...r]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=`Memory ${e.slot}`;return t?M(this.hass,t,i):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id!==t.device_id&&delete i.default_target,i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let o=this._orderedKeys(e),r=o.indexOf(t),c=r+i;if(r<0||c<0||c>=o.length)return;[o[r],o[c]]=[o[c],o[r]];let l=this._cfg;Ai(o,this._presentKeys(e))?delete l.section_order:l.section_order=o,this._emit(l)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let o=this._memorySlots(e),r=this._config?.memory_slots,c=r&&r.length?r.map(Number):[...o];i?c.includes(t)||c.push(t):c=c.filter(u=>u!==t),c.sort((u,m)=>u-m);let l=this._cfg;c.length===o.length?delete l.memory_slots:l.memory_slots=c,this._emit(l)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?h`
      <div class="group">
        <div class="group-title">${_(this.hass,"editor.sections")}</div>
        ${t.map((i,o)=>{let r=this._config?.[`show_${i}`]!==!1;return h`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${o===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${_(this.hass,"editor.move_up")}
                  aria-label=${_(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Mi}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${o===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${_(this.hass,"editor.move_down")}
                  aria-label=${_(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Ci}></path></svg>
                </button>
              </div>
              <ha-switch
                .checked=${r}
                @change=${c=>this._toggleSection(i,c.target.checked)}
              >${_(this.hass,`editor.show_${i}`)}</ha-switch>
            </div>
          `})}
      </div>
    `:p}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return p;let i=e.memory.some(r=>r.save),o=e.memory.length>1;return!i&&!o?p:h`
      <div class="group">
        <div class="group-title">
          ${_(this.hass,"editor.memory_group")}
        </div>
        ${i?h`<div class="row">
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                >${_(this.hass,"editor.memory_save")}</ha-switch>
              </div>`:p}
        ${o?h`<div class="sub">
                <div class="sub-label">
                  ${_(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(r=>h`
                    <div class="row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${c=>this._toggleSlot(e,r.slot,c.target.checked)}
                      >${this._slotLabel(r)}</ha-checkbox>
                    </div>
                  `)}
              </div>`:p}
      </div>
    `}_tapToMoveToggle(){return h`<div class="row">
        <ha-switch .checked=${this._config?.tap_to_move===!0}
          @change=${e=>this._setOption("tap_to_move",e.target.checked||void 0)}
        >${_(this.hass,"editor.tap_to_move")}</ha-switch>
      </div>
      <p class="hint">${_(this.hass,"editor.tap_to_move_hint")}</p>`}_motorsGroup(e){return this._config?.show_motors===!1||!this._presentKeys(e).includes("motors")?p:h`<div class="group">
      <div class="group-title">${_(this.hass,"editor.motors_group")}</div>
      ${this._tapToMoveToggle()}
    </div>`}_setOption(e,t){this._emit({...this._cfg,[e]:t})}_compactToggle(e,t){return h`<div class="row">
      <ha-switch .checked=${this._config?.[e]??t}
        @change=${i=>this._setOption(e,i.target.checked)}
      >${_(this.hass,e==="show_connection"?"editor.compact_connection":`editor.${e}`)}</ha-switch>
    </div>`}_compactGroup(){let e=this._config,t=Le(this.hass,e.device_id),i=t.find(l=>l.key===(e.default_target??"both")),o=t.flatMap(l=>rt(this.hass,l.bed)).filter((l,u,m)=>m.findIndex(g=>g.key===l.key)===u),r=e.compact_actions??(i?Pe(this.hass,i.bed).map(l=>l.key):[]),c=[...r.filter(l=>o.some(u=>u.key===l)),...o.map(l=>l.key).filter(l=>!r.includes(l))];return h`
      <div class="group">
        <div class="group-title">${_(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        <label class="row"><span class="label">${_(this.hass,"editor.compact_labels")}</span>
          <select .value=${e.compact_labels??"angles"}
            @change=${l=>this._setOption("compact_labels",l.target.value)}>
            ${["angles","names","none"].map(l=>h`
              <option value=${l}>${_(this.hass,`editor.labels_${l}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        <label class="row path-row"><span class="label">${_(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${e.navigation_path??""} placeholder="/dashboard/bed"
            @change=${l=>this._setOption("navigation_path",l.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${_(this.hass,"editor.compact_controls")}</div>
        ${t.length>1||!i?h`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${_(this.hass,"editor.default_target")}</span>
            <select .value=${e.default_target??"both"}
              @change=${l=>this._setOption("default_target",l.target.value)}>
              ${i?p:h`<option value=${e.default_target}>${_(this.hass,"compact.target_missing")}</option>`}
              ${t.map(l=>h`<option value=${l.key}>${l.label}</option>`)}
            </select>
          </label>`:p}
        ${this._compactToggle("show_motors",!1)}
        ${e.show_motors===!0?this._tapToMoveToggle():p}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${_(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${_(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${_(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${_(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${_(this.hass,"editor.labels_none")}</button>
        </div>
        ${c.map(l=>{let u=o.find(x=>x.key===l),m=r.includes(l),g=r.indexOf(l),v=x=>{let y=[...r];[y[g],y[g+x]]=[y[g+x],y[g]],this._setOption("compact_actions",y)};return h`<div class="row">
            <ha-checkbox .checked=${m} @change=${x=>this._setOption("compact_actions",x.target.checked?[...r,l]:r.filter(y=>y!==l))}
            >${M(this.hass,u.entityId,l)}</ha-checkbox>
            <button class="icon-btn" ?disabled=${!m||g===0}
              aria-label=${_(this.hass,"editor.move_up")} @click=${()=>v(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!m||g===r.length-1}
              aria-label=${_(this.hass,"editor.move_down")} @click=${()=>v(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return h`<div class="group">
      <label class="row"><span class="label">${_(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${e=>this._setOption("layout",e.target.value)}>
          <option value="full">${_(this.hass,"editor.layout_full")}</option>
          <option value="compact">${_(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${_(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${Kt.map(e=>h`
        <button @click=${()=>this._emit({...Wt(this._config,e)})}>
          ${_(this.hass,`editor.recipe_${e}`)}
        </button>`)}</div>
    </div>`}render(){if(!this.hass||!this._config)return p;let e=this._bed();return h`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():h`
        ${e?this._motorsGroup(e):p}
        ${e?this._sectionsGroup(e):p}
        ${e?this._memoryGroup(e):p}
      `}
    `}};Z.styles=ne`
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
  `,T([Q({attribute:!1})],Z.prototype,"hass",2),T([R()],Z.prototype,"_config",2);ke("adjustable-bed-card-editor",Z);var Ri=new Set(["back","legs","head","feet"]),C=class extends P{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._tapRevision=0;this._watched=[];this._compactStopTargets=new Map;this._hold=new be({pulse:(e,t)=>Ne(this.hass,e,t),holdControl:(e,t)=>Fe(this.hass,e,t),lease:(e,t,i)=>ut(this.hass,e,t,i),stopCover:(e,t)=>this._stopCompactTarget(e,t??e),stopBed:e=>{e&&this._stopCompactTarget(e)},changed:()=>{this._tapRevision++}});this._focusLossCleanup=null;this._windowPointerEnd=e=>{this._hold.endActiveFromPointer(e.pointerId,e.type==="pointercancel"||e.button===0)};this._windowKeyUp=e=>{(e.key==="Enter"||e.key===" ")&&this._hold.endKeyboard(void 0,void 0,e.key)};this._navigate=()=>{let e=Be(this._config?.navigation_path);e&&(this._hold.abandon(),history.pushState(null,"",e),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))};this._openSettings=()=>{this._hold.abandon(),history.pushState(null,"","/config/integrations/integration/adjustable_bed"),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}}))};this._closeEstimateDialog=()=>{let e=this._estimateDialog;e?.kind==="reference"&&e.phase==="lowering"&&this._stopEstimate(e.ctx),this._estimateDialog=void 0}}connectedCallback(){super.connectedCallback(),this._removeHoldLifecycle=bt(this._hold,document,window),window.addEventListener("pointerup",this._windowPointerEnd),window.addEventListener("pointercancel",this._windowPointerEnd),window.addEventListener("keyup",this._windowKeyUp),this._focusLossCleanup=_t(window,document,()=>document.visibilityState==="hidden",()=>this._hold.releaseOnFocusLoss())}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===D)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config&&(this._compactStopTargets.size>0?this._stopCompact():this._hold.abandon()),(e.device_id!==this._config?.device_id||e.default_target!==this._config?.default_target)&&(this._activePairedPane=e.default_target??"both"),this._config=e}getCardSize(){if(this._config?.layout!=="compact")return 8;let e=this._config;return Math.ceil((24+(e.show_header!==!1?36:0)+(e.show_graphic!==!1?150:0)+(e.compact_labels!=="none"?40:0)+(e.compact_actions?.length===0?0:110)+(e.show_motors===!0?180:0)+(e.show_lighting===!0?70:0)+(e.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){window.removeEventListener("pointerup",this._windowPointerEnd),window.removeEventListener("pointercancel",this._windowPointerEnd),window.removeEventListener("keyup",this._windowKeyUp),this._focusLossCleanup?.(),this._focusLossCleanup=null,this._removeHoldLifecycle?.(),this._removeHoldLifecycle=void 0,super.disconnectedCallback(),this._hold.abandon(),this._closeEstimateDialog()}shouldUpdate(e){if(e.has("_config")||e.has("_saveModeFor")||e.has("_activePairedPane")||e.has("_synchronizingTo")||e.has("_synchronizationFailed")||e.has("_estimateDialog")||e.has("_savedEditFor")||e.has("_tapRevision")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices||t.formatEntityName!==this.hass.formatEntityName)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return p;if(!this._config.device_id)return this._notice("card.no_device");let e=$e(this.hass,this._config.device_id),t=se(this.hass,e);if(e&&t.length)return this._renderPaired(e,t);if(this._config.device_id&&we(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=A(this.hass,this._config.device_id);if(this._watched=this._collectWatched(i),j(i))return this._notice("card.no_entities");if(this._config.layout==="compact")return this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:i}],!1);let o=this._config.device_id,r={deviceId:o,paired:!1,sides:[{key:"bed",deviceId:o,label:this._title(),motors:i.motors}],savedPositions:i.savedPositions};return h`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i,"theme",void 0,void 0,void 0,r)}
        ${this._estimateDialogTemplate()}
      </ha-card>
    `}_renderSections(e,t="theme",i,o,r,c){let l=this._config,u={graphic:()=>l.show_graphic!==!1?i??this._graphic(e,t):p,motors:()=>l.show_motors!==!1?this._motors(e,o,r,c):p,firmness:()=>l.show_firmness!==!1?this._firmness(e):p,presets:()=>l.show_presets!==!1?this._presets(e):p,saved_positions:()=>l.show_saved_positions!==!1&&c?this._savedPositions(c):p,memory:()=>l.show_memory!==!1?this._memory(e):p,lighting:()=>l.show_lighting!==!1?this._lighting(e):p,massage:()=>l.show_massage!==!1?this._massage(e):p,utility:()=>l.show_utility!==!1?this._utility(e):p,climate:()=>l.show_climate!==!1?this._climate(e):p,connection:()=>l.show_connection!==!1?this._connection(e):p};return this._orderedSections().map(m=>u[m]?.()??p)}_renderPaired(e,t){let i=this.hass,o=A(i,e),r=t.map((v,x)=>({key:v,label:L(i,v)??v,bed:A(i,v),graphicTone:x===0?"left":"right",synchronizationTarget:{deviceId:v}})),c=r.flatMap(v=>v.bed.stop?[v.bed.stop]:[]),l=o.stop,u=[...new Set([...l?[l]:[],...c])],m=r.map((v,x)=>({key:this._estimateSideKey(v.bed,x),deviceId:v.key,label:v.label,motors:v.bed.motors})),g=[{key:"both",label:_(i,"card.both_sides"),bed:o,stopScope:u,remainingStopIds:c,estimate:{deviceId:e,side:"both",paired:!0,sides:m,savedPositions:o.savedPositions}},...r.map((v,x)=>({...v,stopScope:v.bed.stop?[v.bed.stop]:[],estimate:{deviceId:v.key,paired:!0,sides:[m[x]],savedPositions:o.savedPositions}}))];return this._watched=[o,...r.map(v=>v.bed)].flatMap(v=>this._collectWatched(v)),j(o)&&r.every(v=>j(v.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,g)}_renderSingleAddressPaired(e){let t=this.hass,i={both:A(t,e,"both"),left:A(t,e,"left"),right:A(t,e,"right")},o=[i.left.stop,i.right.stop].filter(r=>r!==void 0);return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>j(r))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:_(t,"card.both_sides"),bed:i.both,stopScope:[...new Set([i.both.stop,...o].filter(r=>r!==void 0))],remainingStopIds:o},{key:"left",label:_(t,"card.left_side"),bed:i.left,graphicTone:"left",stopScope:i.left.stop?[i.left.stop]:[],synchronizationTarget:{deviceId:e,side:"left"}},{key:"right",label:_(t,"card.right_side"),bed:i.right,graphicTone:"right",stopScope:i.right.stop?[i.right.stop]:[],synchronizationTarget:{deviceId:e,side:"right"}}])}_renderPairedCard(e,t){if(this._config?.layout==="compact")return this._renderCompact(e,t,!0);let i=t.filter(l=>!j(l.bed)),o=i.find(l=>l.key===this._activePairedPane)??i[0],r=i.filter(l=>l.key!=="both"),c=o.key==="both";return h`
      <ha-card class="paired-card">
        ${this._header(o.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(l=>h`
              <button
                class="pane-tab side-${l.graphicTone??"theme"} ${l.key===o.key?"active":""}"
                role="tab"
                aria-selected=${l.key===o.key?"true":"false"}
                @click=${()=>this._selectPairedPane(l.key)}
              >
                ${l.graphicTone?h`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span>${l.key==="both"?_(this.hass,"card.both"):l.label}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${o.label}>
          ${this._renderSections(o.bed,o.graphicTone,c?this._pairedOverview(r):void 0,o.stopScope,o.remainingStopIds,o.estimate)}
          ${c&&this._config?.show_lighting!==!1?this._combinedLighting(o.bed,r):p}
          ${c&&this._config?.show_connection!==!1?this._combinedBluetooth(r):p}
        </div>
        ${this._estimateDialogTemplate()}
      </ha-card>
    `}_renderCompact(e,t,i){let o=this._config,r=t.find(b=>b.key===this._activePairedPane),c=r?.bed,l=c?Pe(this.hass,c,o.compact_actions):[],u=o.show_motors===!0&&c?c.motors.filter(b=>b.cover||b.up||b.down||b.position):[],m=l.length>0||u.length>0||o.show_lighting===!0,g=o.compact_actions?.length!==0||o.show_motors===!0||o.show_lighting===!0,v=i?t.filter(b=>b.key!=="both"):t,x=!!c&&He(c).length>0,y=l.length>0||u.length>0,$=Be(o.navigation_path);return h`
      <ha-card class="compact-card ${g?"":"compact-glance"} ${o.animate===!1?"no-animation":""}">
        ${o.show_header!==!1?h`
          <div class="compact-header">
            <span class="title">${this._title(e)}</span>
            ${$?h`<button class="compact-open" @click=${this._navigate}
              aria-label=${_(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:p}
          </div>`:p}
        ${i&&g?o.show_side_selector!==!1?h`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${t.filter(b=>!j(b.bed)).length}`}
            aria-label=${_(this.hass,"compact.target")}>
            ${t.filter(b=>!j(b.bed)).map(b=>h`
              <button class="pane-tab side-${b.graphicTone??"theme"} ${b.key===r?.key?"active":""}"
                aria-pressed=${b.key===r?.key?"true":"false"}
                title=${b.label}
                @click=${()=>this._selectPairedPane(b.key)}>
                ${b.graphicTone?h`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span class="compact-tab-label">${b.key==="both"?_(this.hass,"card.both"):b.label}</span>
              </button>`)}
          </div>`:h`<div class="compact-target">
            ${_(this.hass,"compact.target")}: ${r?.label??_(this.hass,"compact.target_missing")}
          </div>`:p}
        ${o.show_graphic!==!1?this._compactGraphic(v):p}
        ${this._compactReadouts(v)}
        ${!r&&g?h`<div class="hint" role="status">
          ${_(this.hass,"compact.target_missing")}</div>`:p}
        ${u.length?h`<div class="rows compact-motors">
          ${u.map(b=>b.cover||b.up||b.down?this._motorRow(b,c?.stop,!0,r?.stopScope,r?.remainingStopIds):this._moreInfoRow(b.position))}
        </div>`:p}
        ${l.length||y||this._compactStopTargets.size?h`
          <div class="tiles compact-actions">
            ${l.map(({entityId:b})=>h`<button class="tile"
              ?disabled=${!x||!this._available(b)}
              @click=${()=>this._compactRecall(b,c)}>
              ${this._icon(b)}<span class="tile-label">${M(this.hass,b)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!x&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(c)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${_(this.hass,"action.stop")}</span>
            </button>
          </div>`:p}
        ${o.show_lighting===!0&&c?h`
          ${this._lighting(c)}
          ${i&&r?.key==="both"?this._combinedLighting(c,v):p}
        `:p}
        ${o.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(v):h`<div class="compact-connections">
          ${v.map(b=>{let f=this._connectionStatus(b.bed);return f?h`<span>${this._connectionDot(b.bed)}
              ${b.label}: ${_(this.hass,`status.${f}`)}</span>`:p})}
        </div>`:p}
        ${!m&&o.show_graphic===!1&&o.compact_labels==="none"&&o.show_header===!1&&o.show_connection!==!0?h`<div class="hint">${this._title(e)}</div>`:p}
      </ha-card>`}_compactGraphic(e){let t=e.map(u=>this._graphicState(u.bed)),i=t[0],o=t[1],r=t.length>0&&t.every(u=>u!==void 0),c=e.map((u,m)=>`${u.label}: ${t[m]?this._positionSummary(t[m]):_(this.hass,"compact.no_position")}`).join(". "),l=r&&i?o?nt({left:i,right:o}):ot({...i,upper:{angle:i.upper.angle},lower:{angle:i.lower.angle}}):h`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${_(this.hass,"compact.no_position")}</span></div>`;return Be(this._config?.navigation_path)?h`<button class="compact-graphic" @click=${this._navigate}
          aria-label="${_(this.hass,"compact.open")}. ${c}">${l}</button>`:h`<div class="compact-graphic" role="img" aria-label=${c}>${l}</div>`}_compactReadouts(e){let t=this._config?.compact_labels??"angles";return t==="none"?p:h`<div class="compact-readouts ${t==="names"?"compact-names":""}">
      ${e.map(i=>h`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span aria-label=${i.label}>${t==="angles"&&e.length>1?[...i.label][0]:i.label}</span>
        </span>
        ${t==="angles"?h`<span class="compact-position"
          title=${i.bed.motors.map(o=>`${this._motorName(o)} ${this._readout(o)??"?"}`).join(" \xB7 ")}
        >${i.bed.motors.filter(o=>o.angle||o.position||o.cover).map(o=>this._readout(o)??"?").join(" / ")||_(this.hass,"compact.no_position")}</span>`:p}
      </div>`)}
    </div>`}_available(e){let t=this._state(e)?.state;return t!==void 0&&t!=="unavailable"}_compactRecall(e,t){this._hold.abandon(),He(t).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(e),this.requestUpdate()}_stopCompact(e){let t=[...new Set([...e?He(e):[],...this._compactStopTargets.keys()])];this._hold.cancelForStopScope(t);for(let i of t)this._compactStopTargets.has(i)||this._compactStopTargets.set(i,Symbol());for(let i of this._compactStopTargets.keys())this._stopCompactTarget(i);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(e,t=e){let i=this._compactStopTargets.get(t),o=e.startsWith("cover.");this.hass?.callService(o?"cover":"button",o?"stop_cover":"press",{entity_id:e}).then(()=>{i!==void 0&&this._compactStopTargets.get(t)===i&&(this._compactStopTargets.delete(t),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(e){this._activePairedPane!==e&&(this._hold.endTap(),this._activePairedPane=e,this._saveModeFor=void 0,this._savedEditFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.attributes?.state_detail==="connecting"?"connecting":t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?h`<span
      class="connection-dot ${t}"
      title=${_(this.hass,`status.${t}`)}
    ></span>`:p}_pairedOverview(e){let t=e.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(t.length<2)return p;let[i,o]=t;return h`
      <div class="graphic dual-graphic">
        ${nt({left:i.graphic,right:o.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,o].map(({pane:r,graphic:c},l)=>h`
            <div class="dual-readout side-${l===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(c)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,o.pane)}
    `}_synchronizeSelector(e,t){if(!e.synchronizationTarget||!t.synchronizationTarget)return p;let i=this._synchronizationPlan(e.bed,t.bed),o=this._synchronizationPlan(t.bed,e.bed);if(i.length===0&&o.length===0)return p;let r=this._synchronizingTo!==void 0;return h`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${_(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${_(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"left")}
          >
            ${this._synchronizingTo==="left"?h`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:h`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${_(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||o.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"right")}
          >
            ${this._synchronizingTo==="right"?h`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:h`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?h`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${_(this.hass,"sync.incomplete")}</span>
          </div>`:p}
    `}_synchronizationPlan(e,t){let i=new Map(t.motors.map(c=>[c.key,c])),o=e.motors.filter(c=>Ri.has(c.key)&&i.has(c.key)&&this._hasPositionFeedback(c)&&this._hasPositionFeedback(i.get(c.key)));if(o.length===0)return[];let r=o.map(c=>({motor:c.key,position:this._angle(c)}));return r.some(c=>c.position===void 0)||o.some(c=>this._angle(i.get(c.key))===void 0)?[]:r}_hasPositionFeedback(e){return e.angle!==void 0||e.position!==void 0}async _synchronizePositions(e,t,i){if(this._synchronizingTo||!this.hass)return;let o=i==="left"?e:t,r=i==="left"?t:e,c=r.synchronizationTarget;if(!c)return;let l=this._synchronizationPlan(o.bed,r.bed);if(l.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(D,"set_positions",{device_id:[c.deviceId],positions:l,...c.side?{side:c.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,e.lowerMotor]).map(i=>{let o=this._readout(i);return o?`${this._motorName(i)} ${o}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return p;let i=t.map(m=>this._mainLight(m.bed)).filter(m=>m!==void 0);if(i.length===0)return p;let o=i.filter(m=>this._state(m)?.state==="on").length,r=o===i.length,c=o>0,l=r?"combined.on":c?"combined.mixed":"combined.off",u=_(this.hass,"combined.lights");return h`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${c?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${u}</span>
          <span class="secondary">${_(this.hass,l)}</span>
        </div>
        <button
          class="toggle ${c?"on":""} ${c&&!r?"mixed":""}"
          role="switch"
          aria-label=${u}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(e){let t=e.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return t.length===0?p:h`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${t.map(({pane:i,entityId:o})=>{let r=this._connectionStatus(i.bed),l=this._state(o)?.attributes.rssi;return h`
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
                  ${_(this.hass,`status.${r}`)}${typeof l=="number"?` \xB7 ${l} dBm`:""}
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
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){return V(e.lights)}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...q];let t=new Set(q),i=e.filter(r=>t.has(r)),o=q.filter(r=>!i.includes(r));return[...i,...o]}_header(e,t){let i=this._connectionStatus(e),o={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return h`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?p:h`
                <button
                  class="conn ${o[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${_(this.hass,o[i].key)}
                >
                  <ha-icon icon=${o[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?h`
      <div class="graphic">
        ${ot(i,t)}
      </div>
    `:p}_graphicState(e){let t=e.motors.filter(l=>{let u=l.angle??l.position;return u!==void 0&&this._state(u)?.attributes.unit_of_measurement==="\xB0"});if(t.length===0)return this._estimatedGraphicState(e);if(t.some(l=>this._angle(l)===void 0))return;let i=ue(t);if(!i)return;let{upper:o,lower:r}=i,c=e.motors.some(l=>{let u=l.cover?this._state(l.cover)?.state:void 0;return u==="opening"||u==="closing"});return{upperMotor:o,lowerMotor:r,upper:{label:this._motorName(o),angle:this._angle(o)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:c}}_motors(e,t,i,o){let r=t??(e.stop?[e.stop]:[]),c=e.motors.filter(g=>g.cover||g.up||g.down),l=e.motors.filter(g=>g.position&&!g.cover&&!g.up&&!g.down);if(c.length===0&&l.length===0&&!e.synchro&&!e.controlSide&&!e.stop)return p;let u=c.length>0||l.length>0||!!e.synchro||!!e.controlSide,m=o?this._contextEstimates(o):[];return h`
      ${o&&m.length?this._estimateAlertTemplate(o,m):p}
      ${u?this._positionHeading(m):p}
      ${o?.side==="both"?this._estimateOverview(o):p}
      ${e.controlSide?this._moreInfoRow(e.controlSide):p}
      ${e.synchro?this._toggleRow(e.synchro):p}
      ${c.length?h`<div class="rows">
              ${c.map(g=>this._motorRow(g,e.stop,!1,r,i))}
            </div>`:p}
      ${l.length?h`<div class="rows">
              ${l.map(g=>this._moreInfoRow(g.position))}
            </div>`:p}
      ${e.stop?h`<button class="stop-all" @click=${()=>xe(this._hold,e.stop,r,void 0,this.hass)} ?data-armed=${this._hold.tapMoving}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${_(this.hass,"action.stop_all")}</span>
            </button>`:p}
    `}_firmness(e){return e.firmness.length===0?p:h`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t,i=!1,o,r){let c=this._hold.tapDirection(e),l=c?_(this.hass,`tap.moving_${c}`):this._readout(e),u=!!e.cover||!!t,m=h`
      <span>${this._motorName(e)}</span>
      ${l&&!i?h`<span class="readout ${c?"moving":""}">${l}</span>`:p}
    `;return h`
      <div class="row">
        ${e.position?h`<button
              class="row-label position-label"
              aria-label=${M(this.hass,e.position)}
              @click=${()=>this._moreInfo(e.position)}
            >${m}</button>`:h`<div class="row-label">${m}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(e,"down",t,o,r):p}
          ${this._motorDirection(e,"up",t,o,r)}
          ${i?p:h`<button
            class="cg-btn"
            aria-label=${_(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e,t,o)}
            ?disabled=${!u}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?p:this._motorDirection(e,"down",t,o,r)}
        </div>
      </div>
    `}_motorDirection(e,t,i,o,r){let c=e.cover??e[t],l=!!e.cover||!!i,u=!c||this._config?.layout==="compact"&&(!l||!this._available(c));if(this._config?.tap_to_move===!0&&ht(e,t)){let m=this._hold.tapDirection(e)===t;return h`
        <button class="cg-btn tap ${m?"moving":""}"
          aria-label=${_(this.hass,`action.${t}`)}
          aria-pressed=${m?"true":"false"}
          @click=${()=>this._tapMove(e,t,i,o,r)}
          ?disabled=${u&&!m}
        ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}return h`
      <button class="cg-btn"
        aria-label=${_(this.hass,`action.${t}`)}
        @pointerdown=${m=>this._startHold(m,e,t,i,o,r)}
        @pointerup=${m=>this._endPointerHold(m,e,i)}
        @pointercancel=${m=>this._endPointerHold(m,e,i)}
        @keydown=${m=>this._startHold(m,e,t,i,o,r)}
        @keyup=${m=>this._endKeyHold(m,e,i)}
        @blur=${()=>this._hold.endKeyboard(e,i)}
        @click=${m=>this._activateWithoutPointer(m,e,t,i,o)}
        ?disabled=${u}
      ><ha-icon icon=${`mdi:chevron-${t}`}></ha-icon></button>`}_presets(e){return e.presets.length===0?p:h`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._actionTile(t,e.stop))}
      </div>
    `}_utility(e){return e.utility.length===0&&!e.utilityNumbers?.length&&!e.utilitySelects?.length&&!e.utilityStates?.length?p:h`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${e.utility.map(t=>this._actionTile(t,e.stop,()=>t.startsWith("switch.")?this._call("switch","toggle",t):this._press(t)))}
      </div>
      ${e.utilitySelects?.map(t=>this._moreInfoRow(t))}
      ${e.utilityNumbers?.map(t=>this._moreInfoRow(t))}
      ${e.utilityStates?.map(t=>this._moreInfoRow(t))}
    `}_actionTile(e,t,i=()=>this._press(e)){let o=mt(this.hass,e);return o?this._heldActionTile(e,o,t):this._tile(e,i)}_heldActionTile(e,t,i){return h`<button class="tile"
      aria-label=${M(this.hass,e)}
      @pointerdown=${o=>this._startHold(o,t,"up",i)}
      @pointerup=${o=>this._endPointerHold(o,t,i)}
      @pointercancel=${o=>this._endPointerHold(o,t,i)}
      @keydown=${o=>this._startHold(o,t,"up",i)}
      @keyup=${o=>this._endKeyHold(o,t,i)}
      @blur=${()=>this._endHold(t,i)}
      @click=${o=>this._activateWithoutPointer(o,t,"up",i)}
      ?disabled=${!i||!this._available(e)}>
      ${this._icon(e)}
      <span class="tile-label">${M(this.hass,e)}</span>
    </button>`}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let l=new Set(i.map(Number));t=t.filter(u=>l.has(u.slot))}if(t.length===0)return p;let o=this._config?.memory_save!==!1&&t.some(l=>l.save),r=t.map(l=>l.save??l.goto??String(l.slot)).join("|"),c=this._saveModeFor===r;return h`
      <div class="section-heading heading-row">
        <span>${_(this.hass,"section.memory")}</span>
        ${o?h`<button
                class="set-btn ${c?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${c?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${_(this.hass,c?"memory.cancel":"memory.set")}</span>
              </button>`:p}
      </div>
      ${c?h`<div class="hint">${_(this.hass,"memory.set_hint")}</div>`:p}
      <div class="tiles">${t.map(l=>this._memoryTile(l,c,e.stop))}</div>
    `}_memoryTile(e,t,i){let o=e.goto??e.save;if(t){let c=!!e.save;return h`
        <button
          class="tile ${c?"save-mode":"is-disabled"}"
          ?disabled=${!c}
          @click=${()=>c&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${M(this.hass,o)}</span>
        </button>
      `}let r=!!e.goto;return r?this._actionTile(e.goto,i):h`
      <button
        class="tile ${r?"":"is-disabled"}"
        ?disabled=${!r}
        @click=${()=>e.goto&&this._press(e.goto)}
      >
        ${this._icon(o)}
        <span class="tile-label">${M(this.hass,o)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;if(!V(t)&&!t.state)return p;let o=i||t.state||t.level||t.numbers?.length||t.timer||t.toggle||t.cycle||t.timerMinutes||t.timerToggle||t.buttons?.length;return h`
      ${this._heading("section.lighting")}
      ${t.mood&&o?this._subheading("lighting.floor"):p}
      ${i?this._toggleRow(i):p}
      ${t.state?this._moreInfoRow(t.state):p}
      ${t.states?.map(r=>this._moreInfoRow(r))}
      ${t.level?this._moreInfoRow(t.level):p}
      ${t.numbers?.map(r=>this._moreInfoRow(r))}
      ${t.timer?this._moreInfoRow(t.timer):p}
      ${t.timerMinutes?this._moreInfoRow(t.timerMinutes):p}
      ${!t.timerAppliesImmediately&&(t.timerMinutes||t.timerToggle)?h`<div class="hint">${_(this.hass,"lighting.timer_pending")}</div>`:p}
      ${t.toggle||t.cycle||t.timerToggle||t.buttons?.length?h`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):p}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):p}
              ${t.timerToggle?this._tile(t.timerToggle,()=>this._press(t.timerToggle)):p}
              ${t.buttons?.map(r=>this._actionTile(r,e.stop))}
            </div>`:p}
      ${t.mood?h`
        ${this._subheading("lighting.mood")}
        ${t.mood.selects.map(r=>this._moreInfoRow(r))}
        ${t.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${t.mood.toggle||t.mood.buttons?.length?h`<div class="tiles">
          ${t.mood.toggle?this._tile(t.mood.toggle,()=>this._press(t.mood.toggle)):p}
          ${t.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:p}
      `:p}
    `}_massage(e){let t=e.massage;return t.buttons.length===0&&t.numbers.length===0&&!t.selects?.length&&!t.states?.length&&!t.timer?p:h`
      ${this._heading("section.massage")}
      ${t.buttons.length?h`<div class="tiles">
              ${t.buttons.map(i=>this._actionTile(i,e.stop))}
            </div>`:p}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.selects?.map(i=>this._moreInfoRow(i))}
      ${t.states?.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):p}
    `}_climate(e){let t=[...e.climate.entities,...e.climate.selects,...e.climate.numbers];return t.length===0?p:h`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?p:h`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):p}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):p}
      </div>
    `}_heading(e){return h`<div class="section-heading">${_(this.hass,e)}</div>`}_subheading(e){return h`<div class="lighting-heading">${_(this.hass,e)}</div>`}_tile(e,t,i={}){return h`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${M(this.hass,e)}</span>
      </button>
    `}_onRowKey(e,t){e.target===e.currentTarget&&(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),t())}_toggleRow(e){let i=this._state(e)?.state==="on",o=M(this.hass,e);return h`
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
    `}_moreInfoRow(e){let t=M(this.hass,e);return h`
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
    `}_icon(e,t){let i=this._state(e);return i?h`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:h`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return h`<ha-card><div class="notice">${_(this.hass,e)}</div></ha-card>`}_estimateSideKey(e,t){let i=[e.estimateRemote,e.stop,...e.motors.flatMap(o=>[o.estimate,o.reference])];for(let o of i){let r=o?this._state(o)?.attributes.bed_side:void 0;if(r==="left"||r==="right")return r}return t===0?"left":"right"}_t(e,t){return _(this.hass,e,t)}_contextEstimates(e){return e.sides.flatMap(t=>me(this.hass,t.motors))}_estimatesByKey(e){return Object.fromEntries(e.sides.map(t=>[t.key,me(this.hass,t.motors)]))}_estimateService(e,t,i={}){return this.hass?.callService(D,e,{device_id:t.deviceId,...t.side?{side:t.side}:{},...i})??Promise.resolve()}_toast(e){this.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:e},bubbles:!0,composed:!0}))}_positionHeading(e){let t=It(e);return t?h`<div class="section-heading heading-row">
      <span>${this._t("section.position")}</span>
      <span class="estimate-chip chip-${t}">${this._t(`estimate.chip_${t}`)}</span>
    </div>`:this._heading("section.position")}_estimateValues(e){return e.map(t=>`${this._motorName({key:t.motor})} ${X({...t,state:t.percent===void 0?"unknown":"tracking"},(i,o)=>this._t(i,o))}`).join(", ")}_estimateAlertTemplate(e,t){let i=Ut(t);if(!i)return p;let o,r,c=h`<button class="set-btn" @click=${()=>this._openReference(e)}>
      ${this._t("estimate.set_reference")}</button>`;if(i.kind==="calibrate")o=this._t("estimate.alert_calibrate"),r=h`<button class="set-btn" @click=${this._openSettings}>
        ${this._t("estimate.calibrate_now")}</button>`;else if(i.kind==="unconfirmed")o=this._t("estimate.alert_unconfirmed",{values:this._estimateValues(i.estimates)}),r=h`<button class="set-btn" @click=${()=>void this._estimateService("confirm_position_unchanged",e).catch(()=>{})}>
        ${this._t("estimate.unchanged")}</button>${c}`;else{let l=`estimate.reason_${i.reason??"not_referenced"}`,u=this._t(l);o=this._t("estimate.alert_unknown",{reason:u===l?this._t("estimate.reason_not_referenced"):u}),r=c}return h`<div class="estimate-alert alert-${i.kind}" role="status">
      <ha-icon icon=${i.kind==="calibrate"?"mdi:tune-variant":"mdi:alert-outline"}></ha-icon>
      <span class="estimate-alert-text">${o}</span>
      <div class="estimate-alert-actions">${r}</div>
    </div>`}_estimateOverview(e){let t=e.sides.flatMap(i=>{let o=me(this.hass,i.motors);return o.length?[{side:i,estimates:o}]:[]});return t.length===0?p:h`<div class="estimate-overview">
      ${t.map(({side:i,estimates:o})=>h`<div class="estimate-overview-row">
        <span class="estimate-overview-side">${i.label}</span>
        ${je(o)?h`<span>${o.map(r=>`${this._motorName({key:r.motor})} ${X(r,(c,l)=>this._t(c,l))}`).join(" \xB7 ")}</span>`:h`<span>${this._t("estimate.unknown")} ·
              <button class="link-btn" @click=${()=>this._openReference({deviceId:i.deviceId,paired:!0,sides:[i],savedPositions:e.savedPositions})}>${this._t("estimate.set_reference")}</button></span>`}
      </div>`)}
    </div>`}_savedPositions(e){if(!e.savedPositions)return p;let t=this._contextEstimates(e),i=Vt(qt(this.hass,e.savedPositions),e.sides.map(l=>l.key));if(t.length===0&&i.length===0)return p;let o=this._estimatesByKey(e),r=this._savedEditFor===e.deviceId,c=je(t);return h`
      <div class="section-heading heading-row">
        <span>${this._t("section.saved_positions")}</span>
        ${i.length?h`<button class="set-btn ${r?"active":""}"
              @click=${()=>{this._savedEditFor=r?void 0:e.deviceId}}>
              <ha-icon icon=${r?"mdi:check":"mdi:pencil-outline"}></ha-icon>
              <span>${this._t(r?"estimate.done":"estimate.edit")}</span>
            </button>`:p}
      </div>
      ${r?h`<div class="hint">${this._t("estimate.edit_hint")}</div>`:p}
      <div class="tiles">
        ${i.map(l=>{let u=Jt(l,o),m=e.paired?Yt(l):"bed";return h`<button
            class="tile ${r?"save-mode":""} ${!r&&!u?"is-disabled":""}"
            ?disabled=${!r&&!u}
            @click=${()=>r?this._openEdit(e,l):this._recall(e,l)}>
            <ha-icon class="icon" icon=${r?"mdi:pencil-outline":"mdi:bookmark-outline"}></ha-icon>
            <span class="tile-label">${l.name}</span>
            ${m!=="bed"?h`<span class="tile-sublabel">${this._t(`estimate.scope_${m}`)}</span>`:p}
          </button>`})}
        <button class="tile ${c?"":"is-disabled"}" ?disabled=${!c}
          @click=${()=>{this._estimateDialog={kind:"save",ctx:e,name:"",button:!0}}}>
          <ha-icon class="icon" icon="mdi:bookmark-plus-outline"></ha-icon>
          <span class="tile-label">${this._t("estimate.save")}</span>
        </button>
      </div>
      <div class="hint estimate-footer">${this._t("estimate.footer")}</div>
    `}_recall(e,t){this._hold.abandon(),this._estimateService("recall_position",{...e,side:void 0},{position:t.id}).then(()=>this._toast(this._t("estimate.recalled",{name:t.name}))).catch(()=>{})}_openReference(e){this._estimateDialog={kind:"reference",ctx:e,choice:"flat",phase:"choose"}}_openEdit(e,t){this._estimateDialog={kind:"edit",ctx:e,position:t,name:t.name,button:t.button}}_stopEstimate(e){this._estimateService("stop_all",e).catch(()=>{})}updated(e){super.updated(e);let t=this.renderRoot?.querySelector?.("dialog.estimate-dialog");t&&!t.open&&t.showModal()}_estimateDialogTemplate(){let e=this._estimateDialog;if(!e)return p;let t=e.kind==="reference"?this._referenceDialog(e):e.kind==="save"?this._saveDialog(e):this._editDialog(e);return h`<dialog class="estimate-dialog" @close=${this._closeEstimateDialog}>
      ${t}
    </dialog>`}_dialogMotors(e){let t=this._contextEstimates(e).filter(i=>i.state!=="not_calibrated").map(i=>i.motor);return[...new Set(t)]}_referenceDialog(e){let t=this._dialogMotors(e.ctx),i=t.map(m=>this._motorName({key:m})).join(", "),o=[{value:"flat",title:this._t("estimate.ref_flat"),detail:this._t("estimate.ref_flat_detail",{motors:i})},{value:"lower",title:this._t("estimate.ref_lower"),detail:this._t("estimate.ref_lower_detail")},...t.length>1?t.map(m=>({value:`only:${m}`,title:this._t("estimate.ref_only",{motor:this._motorName({key:m})}),detail:this._t("estimate.ref_only_detail")})):[]],r=e.choice==="lower"&&e.phase==="choose",c=e.choice.startsWith("only:")?[e.choice.slice(5)]:t,l=()=>{if(e.phase!=="lowering"){if(r){let m={...e,phase:"lowering"};this._estimateDialog=m,this._estimateService("lower_to_flat",e.ctx).then(()=>{this._estimateDialog===m&&(this._estimateDialog={...e,phase:"lowered"})},()=>{this._estimateDialog===m&&(this._estimateDialog={...e,phase:"choose"})});return}this._estimateService("set_position_reference",e.ctx,{motors:c}).catch(()=>{}),this._estimateDialog=void 0}},u=e.phase==="lowering"?"estimate.ref_lowering_running":e.phase==="lowered"?"estimate.ref_lowering":"estimate.ref_text";return h`
      <h2>${this._t("estimate.ref_title")}</h2>
      <p class="dialog-text">${this._t(u)}</p>
      ${e.phase!=="choose"?p:h`<div class="dialog-choices" role="radiogroup">
        ${o.map(m=>h`<label class="dialog-choice">
          <input type="radio" name="reference" .checked=${e.choice===m.value}
            @change=${()=>{this._estimateDialog={...e,choice:m.value}}} />
          <span><strong>${m.title}</strong><span class="dialog-detail">${m.detail}</span></span>
        </label>`)}
      </div>`}
      <div class="dialog-actions">
        ${e.phase==="lowering"?h`<button class="dialog-btn danger" @click=${()=>{this._stopEstimate(e.ctx),this._estimateDialog={...e,phase:"choose"}}}>${this._t("action.stop")}</button>`:p}
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" ?disabled=${e.phase==="lowering"} @click=${l}>
          ${this._t(r?"estimate.ref_lower_start":"estimate.ref_confirm")}</button>
      </div>`}_estimateList(e){return h`<div class="dialog-values">
      ${e.sides.flatMap(t=>me(this.hass,t.motors).map(i=>h`
        <div class="dialog-value"><span>${e.paired?`${t.label} `:""}${this._motorName({key:i.motor})}</span>
          <span>${X(i,(o,r)=>this._t(o,r))}</span></div>`))}
    </div>`}_saveDialog(e){let t=e.name.trim(),i=()=>{t&&(this._estimateService("save_position",e.ctx,{name:t,create_button:e.button}).catch(()=>{}),this._estimateDialog=void 0)};return h`
      <h2>${this._t("estimate.save_title")}</h2>
      <label class="dialog-field"><span>${this._t("estimate.name")}</span>
        <input type="text" maxlength="40" .value=${e.name}
          @input=${o=>{this._estimateDialog={...e,name:o.target.value}}} />
      </label>
      ${this._estimateList(e.ctx)}
      <label class="dialog-check">
        <input type="checkbox" .checked=${e.button}
          @change=${o=>{this._estimateDialog={...e,button:o.target.checked}}} />
        <span><strong>${this._t("estimate.create_button")}</strong>
          <span class="dialog-detail">${this._t("estimate.create_button_detail")}</span></span>
      </label>
      <p class="dialog-text">${this._t("estimate.save_note")}</p>
      <div class="dialog-actions">
        <button class="dialog-btn" @click=${this._closeEstimateDialog}>${this._t("memory.cancel")}</button>
        <button class="dialog-btn primary" ?disabled=${!t} @click=${i}>${this._t("estimate.save_confirm")}</button>
      </div>`}_editDialog(e){let{position:t,ctx:i}=e,o=this._estimatesByKey(i),c=Object.keys(t.beds).every(g=>je(o[g]??[])),l=e.name.trim(),u=(g,v={})=>{this._estimateService(g,{...i,side:void 0},{position:t.id,...v}).catch(()=>{}),this._estimateDialog=void 0},m=g=>g==="bed"?"":`${this._t(`card.${g}_side`)} `;return h`
      <h2>${this._t("estimate.edit_title",{name:t.name})}</h2>
      <label class="dialog-field"><span>${this._t("estimate.name")}</span>
        <input type="text" maxlength="40" .value=${e.name}
          @input=${g=>{this._estimateDialog={...e,name:g.target.value}}} />
      </label>
      <div class="dialog-values">
        <div class="dialog-value dialog-value-head"><span></span>
          <span>${this._t("estimate.saved")}</span><span>${this._t("estimate.now")}</span></div>
        ${Object.entries(t.beds).flatMap(([g,v])=>Object.entries(v).map(([x,y])=>{let $=o[g]?.find(b=>b.motor===x);return h`<div class="dialog-value">
              <span>${m(g)}${this._motorName({key:x})}</span>
              <span>${Math.round(y)}%</span>
              <span>${$?X($,(b,f)=>this._t(b,f)):"-"}</span>
            </div>`}))}
      </div>
      <label class="dialog-check">
        <input type="checkbox" .checked=${e.button}
          @change=${g=>{this._estimateDialog={...e,button:g.target.checked}}} />
        <span><strong>${this._t("estimate.create_button")}</strong>
          <span class="dialog-detail">${this._t("estimate.create_button_detail")}</span></span>
      </label>
      ${c?p:h`<p class="dialog-text">${this._t("estimate.update_blocked")}</p>`}
      <div class="dialog-actions">
        <button class="dialog-btn danger" @click=${()=>u("delete_position")}>${this._t("estimate.delete")}</button>
        <button class="dialog-btn" ?disabled=${!c} @click=${()=>u("update_position")}>${this._t("estimate.update")}</button>
        <button class="dialog-btn primary" ?disabled=${!l}
          @click=${()=>u("rename_position",{name:l,create_button:e.button})}>${this._t("estimate.save_confirm")}</button>
      </div>`}_estimatedGraphicState(e){let t=c=>Qt(De(this.hass,c)),i=ue(e.motors.filter(c=>t(c)!==void 0));if(!i)return;let{upper:o,lower:r}=i;return{upperMotor:o,lowerMotor:r,upper:{label:this._motorName(o),angle:t(o)},lower:{label:this._motorName(r),angle:t(r)},moving:!1,estimated:!0}}_state(e){return this.hass?.states[e]}_title(e=this._config?.device_id){return this._config?.name?this._config.name:L(this.hass,e)??_(this.hass,"card.default_name")}_motorName(e){let t=`motor.${e.key}`,i=_(this.hass,t);return i!==t?i:e.key.split("_").map(o=>o.charAt(0).toUpperCase()+o.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){let t=e.angle??e.position;if(t){let o=this._angle(e);if(o===void 0)return;let r=this._state(t)?.attributes.unit_of_measurement,c=e.angle?"\xB0":"%";return`${Math.round(o)}${typeof r=="string"?r:c}`}let i=De(this.hass,e);if(i)return X(i,(o,r)=>_(this.hass,o,r));if(e.cover){let o=this._state(e.cover)?.attributes.current_position;return typeof o=="number"?`${Math.round(o)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position,i.estimate,i.reference].forEach(o=>o&&t.add(o));[e.estimateRemote,e.savedPositions].forEach(i=>i&&t.add(i)),e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(o=>o&&t.add(o));return[e.stop,e.synchro,e.controlSide,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.state,...e.lights.states??[],e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.lights.timerMinutes,e.lights.timerToggle,e.lights.mood?.toggle,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.lights.buttons?.forEach(i=>t.add(i)),e.lights.numbers?.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.massage.selects?.forEach(i=>t.add(i)),e.massage.states?.forEach(i=>t.add(i)),e.lights.mood?.selects.forEach(i=>t.add(i)),e.lights.mood?.numbers.forEach(i=>t.add(i)),e.lights.mood?.buttons?.forEach(i=>t.add(i)),e.utility.forEach(i=>t.add(i)),e.utilityNumbers?.forEach(i=>t.add(i)),e.utilitySelects?.forEach(i=>t.add(i)),e.utilityStates?.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),e.climate.numbers.forEach(i=>t.add(i)),[...t]}_startHold(e,t,i,o,r,c){let l=null;if(e instanceof KeyboardEvent){if(e.key!=="Enter"&&e.key!==" "||(e.preventDefault(),e.repeat))return}else{if(e.button!==0||!e.isPrimary)return;e.currentTarget.setPointerCapture?.(e.pointerId),e.preventDefault(),l=e.pointerId}if(this._hold.tapMoving){this._hold.endTap();return}this._markCompactTarget(t,o),this._hold.start(t,i,l,o,r??(o?[o]:[]),c,e instanceof KeyboardEvent?e.key:null,U(this.hass,o??t.holdEntityId??t.cover??t[i]))}_activateWithoutPointer(e,t,i,o,r){e.detail!==0||this._hold.heldKey!==null||(this._markCompactTarget(t,o),this._hold.claimStopScope([...r??[],...o?[o]:[],...t.cover?[t.cover]:[]],U(this.hass,o??t.holdEntityId??t.cover??t[i])),gt(this.hass,t,i))}_tapMove(e,t,i,o,r){this._hold.tapMoving||this._markCompactTarget(e,i),this._hold.tap(e,t,i,o??(i?[i]:[]),r,U(this.hass,i??e.holdEntityId??e.cover??e[t]))}_markCompactTarget(e,t){this._config?.layout==="compact"&&(t?this._compactStopTargets.set(t,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate())}_endPointerHold(e,t,i){this._hold.endFromPointer(t,e.pointerId,e.type!=="pointerup"||e.button===0,i)}_endKeyHold(e,t,i){e.key!=="Enter"&&e.key!==" "||(e.stopPropagation(),this._hold.endKeyboard(t,i,e.key))}_endHold(e,t){this._hold.end(e,t)}_motorStop(e,t,i){if(e.cover){i?.length?xe(this._hold,e.cover,[...i,e.cover],e.coverStopScope==="side"?void 0:e.key,this.hass):(this._hold.stopCover(e,U(this.hass,e.cover),e.coverStopScope??"motor",t,Ke(this.hass,e.cover)),this._cover(e.cover,"stop_cover"));return}xe(this._hold,t,i,void 0,this.hass)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};C.styles=ne`
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
    .dual-bed-side.is-estimated .dual-bed-surface {
      fill-opacity: 0.45;
      stroke: currentColor;
      stroke-width: 1.5;
      stroke-dasharray: 5 4;
    }
    .bed-graphic.is-estimated .bed-surface {
      fill-opacity: 0.45;
      stroke: rgb(var(--ab-graphic-rgb));
      stroke-width: 1.5;
      stroke-dasharray: 5 4;
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
  `,T([Q({attribute:!1})],C.prototype,"hass",2),T([R()],C.prototype,"_config",2),T([R()],C.prototype,"_saveModeFor",2),T([R()],C.prototype,"_activePairedPane",2),T([R()],C.prototype,"_synchronizingTo",2),T([R()],C.prototype,"_synchronizationFailed",2),T([R()],C.prototype,"_estimateDialog",2),T([R()],C.prototype,"_savedEditFor",2),T([R()],C.prototype,"_tapRevision",2);ke("adjustable-bed-card",C);console.info(`%c adjustable-bed-card %c ${Xt} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{C as AdjustableBedCard};
