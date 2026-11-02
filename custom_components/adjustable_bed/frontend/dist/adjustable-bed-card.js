/* adjustable-bed-card 4.2.4 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var ye=Object.defineProperty;var xe=Object.getOwnPropertyDescriptor;var w=(n,s,t,e)=>{for(var i=e>1?void 0:e?xe(s,t):s,o=n.length-1,r;o>=0;o--)(r=n[o])&&(i=(e?r(s,t,i):r(i))||i);return e&&i&&ye(s,t,i),i};var B="adjustable_bed";function q(n){for(let s of["left","right","both"]){let t=`_${s}`;if(n.endsWith(t))return{key:n.slice(0,-t.length),side:s}}return{key:n}}var F=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],Kt=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],$t=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_swing","preset_incline","preset_both_up","preset_yoga"],$e={back:"back",foot:"feet",pillow:"pillow"},we=new Set(["elevate_both","starcode_m1x12_part_1","starcode_m1x12_part_2","starcode_m1x12_part_4","starcode_m1x12_part_8","starcode_m1x12_part_16"]),ke=n=>n.split(".",1)[0],wt=n=>n.translation_key??"";function Se(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[]}}function x(n,s,t){let e=Se();if(!s||!n?.entities)return e;let i=()=>e.lights.mood??={selects:[],numbers:[]},o=n.devices?.[s]?.parent_device_id||Object.values(n.devices??{}).some(u=>u.parent_device_id===s),r=Object.values(n.entities).filter(u=>u.device_id===s&&u.platform===B),a=!!t||!!o&&!r.some(u=>u.translation_key==="ble_connection"),c=new Map,h=u=>{let d=c.get(u);return d||(d=we.has(u)?{key:u,coverStopScope:"side"}:{key:u},c.set(u,d)),d},f=new Map,_=new Map,v=u=>{let d=_.get(u);return d||(d={slot:u},_.set(u,d)),d};for(let u of r){if(u.hidden)continue;let d=u.entity_id,ve=ke(d),xt=wt(u);if(!xt)continue;let P=q(xt),Ut=n.states[d]?.attributes.bed_side??n.states[d]?.attributes.side??P.side;if(t&&Ut!==t)continue;let l=a&&P.side===Ut?P.key:xt,E;switch(ve){case"cover":{let R=h(l);R.cover=d;let N=n.states[d]?.attributes;(l==="back"||l==="legs"||l==="lumbar")&&typeof N?.held_control_up=="string"&&typeof N?.held_control_down=="string"&&(R.timedMove={deviceId:s,motor:l})}break;case"sensor":l.endsWith("_angle")?h(l.slice(0,-6)).angle=d:l.startsWith("reverie_")&&l.endsWith("_massage_intensity")?(e.massage.states??=[]).push(d):l==="reverie_pairlink_massage_mode"||l==="reverie_pairlink_massage_timer"?(e.massage.states??=[]).push(d):l==="reverie_massage_wave"?(e.massage.states??=[]).push(d):l==="logicdata_air_pump_pressure"?e.firmness.push(d):l==="innova_massage_timer"&&(e.massage.timer=d);break;case"number":l.endsWith("_position")?h(l.slice(0,-9)).position=d:l==="reverie_body_tilt"?h("lumbar").position=d:!t&&P.side&&P.key.endsWith("_position")?h(`${P.key.slice(0,-9)}_${P.side}`).position=d:l.startsWith("massage_")&&l.endsWith("_intensity")||l==="reverie_wave_level"||l==="reverie_massage_wave"||l==="reverie_stk_head_wave"||l==="reverie_stk_global_massage"?e.massage.numbers.push(d):l==="reverie_pairlink_massage_timer"?e.massage.timer=d:l==="light_level"||l==="svane_intensity"||l==="starcode_brightness"||l==="vmatbasic_floor_level"||l==="starcode_abm5_4_light_level"?e.lights.level=d:l==="vmatbasic_floor_minutes"?(e.lights.timerMinutes=d,e.lights.timerAppliesImmediately=!0):l==="vibradorm_app_floor_timer_minutes"?e.lights.timerMinutes=d:(E=l.match(/^richmat_mh_(back|foot|pillow)_angle$/))?h($e[E[1]]).position=d:l==="richmat_mh_light_timer"?e.lights.timer=d:l==="richmat_mh_light_timer_minutes"?(e.lights.timerMinutes=d,e.lights.timerAppliesImmediately=!0):l==="richmat_mh_head_massage_intensity"||l==="richmat_mh_foot_massage_intensity"?e.massage.numbers.push(d):l==="vibradorm_app_mood_speed"||l==="vmatbasic_mood_speed"||l==="vmatbasic_mood_brightness"?i().numbers.push(d):l==="vibradorm_app_massage_speed"||l==="sleeptracker_wave_minutes"?e.massage.numbers.push(d):/^sleeptracker_(left|right)_level$/.test(l)||l==="fan_level"?e.climate.numbers.push(d):l.startsWith("sleep_number_setting")&&e.firmness.push(d);break;case"button":if($t.includes(l)||l.startsWith("preset_"))(E=l.match(/^preset_memory_(\d+)$/))?v(Number(E[1])).goto=d:f.set(l,d);else if(E=l.match(/^program_memory_(\d+)$/))v(Number(E[1])).save=d;else if(l==="stop"||l==="stop_both")e.stop=d;else if(l==="connect")e.connect=d;else if(l==="disconnect")e.disconnect=d;else if(l==="sleeptracker_light_toggle")e.lights.toggle=d;else if(l==="sleeptracker_light_off")(e.lights.buttons??=[]).push(d);else if(/^sleeptracker_(massage_|wave_start|wind_down_|local_animation)/.test(l))e.massage.buttons.push(d);else if(l.startsWith("sleeptracker_"))e.utility.push(d);else if(l==="toggle_light")e.lights.toggle=d;else if(l==="light_cycle"||l==="starcode_light_cycle")e.lights.cycle=d;else if(l==="vibradorm_app_mood_toggle"||l==="vmatbasic_mood_toggle")i().toggle=d;else if(l==="vmatbasic_mood_nightlight")(i().buttons??=[]).push(d);else if(l==="vmatbasic_floor_toggle"||l==="vmatbasic_floor_hold")e.lights.toggle=d;else if(l.startsWith("vmatbasic_massage_"))e.massage.buttons.push(d);else if(l==="vibradorm_app_floor_timer_toggle")e.lights.timerToggle=d;else if(l==="remacro_led_brightness_save")(e.lights.buttons??=[]).push(d);else if(l==="starcode_abm5_4_light_plus"||l==="starcode_abm5_4_light_minus"||l==="starcode_abm5_4_light_on"||l==="starcode_abm5_4_light_off")(e.lights.buttons??=[]).push(d);else if(l==="starcode_abm5_4_massage_release")e.massage.buttons.push(d);else if(l.startsWith("starcode_abm5_4_"))e.utility.push(d);else if(l==="okin_app_home")f.set(l,d);else if(l.startsWith("simmons_inclined"))f.set(l,d);else if(l==="simmons_sync_clock"||l==="simmons_refresh_alarms")e.utility.push(d);else if(l==="richmat_mh_massage")e.massage.buttons.push(d);else if(l==="richmat_mh_preset")f.set(`${l}:${d}`,d);else if(l.startsWith("richmat_mh_"))e.utility.push(d);else if(l.startsWith("adjustable_lumbar_wave_")||l==="adjustable_lumbar_massage_on")e.massage.buttons.push(d);else if(l.startsWith("adjustable_lumbar_"))e.utility.push(d);else if(l==="logicdata_app_query_massage")e.massage.buttons.push(d);else if(l.startsWith("logicdata_air_pump_"))e.utility.push(d);else if(l==="ore_comfort_massage_start"||l==="innova_massage_level"||l==="innova_massage_timer_hold")e.massage.buttons.push(d);else if(l==="ore_comfort_program_flat"||l==="ore_comfort_program_zero_g")e.utility.push(d);else if(l==="coolbase_head_massage"||l==="coolbase_foot_massage"||l==="coolbase_massage_mode")e.massage.buttons.push(d);else if(l==="restonic_zzz")e.utility.push(d);else if(l.startsWith("coolbase_"))e.utility.push(d);else if(l==="vibradorm_app_massage_automatic"||l==="vibradorm_app_massage_individual")e.massage.buttons.push(d);else if(l==="sync_positions"||l==="child_lock_toggle"||l==="auxiliary_action"||l==="remote_action"||l==="solace_music_toggle"||l==="solace_music_off"||l==="wake_controller"||l==="reset_defaults"||l==="factory_reset"||l==="vibradorm_app_all_up"||l==="vibradorm_app_all_down"||l==="vibradorm_app_sync"||l==="vibradorm_app_refresh_info"||l==="vmatbasic_all_up"||l==="vmatbasic_all_down"||l==="vmatbasic_refresh_info"||l.startsWith("starcode_save_")||l==="starcode_reset"||l==="starcode_query"||l==="starcode_light_mode")e.utility.push(d);else if(l.startsWith("massage_"))e.massage.buttons.push(d);else if(E=l.match(/^(.+)_(up|down)$/)){let R=E[1],N=h(R);N[E[2]]=d;let Gt=R==="back"?"back":R==="legs"?"legs":R==="lumbar"?"lumbar":void 0,ot=n.states[d]?.attributes.paired_hold_motor;if(ot==="back"||ot==="legs"||ot==="lumbar"){let be=n.states[d]?.attributes.paired_hold_side;N.timedMove={deviceId:s,motor:ot,...be==="both"?{side:"both"}:{}}}else Gt!==void 0&&typeof n.states[d]?.attributes.held_control=="string"&&(N.timedMove={deviceId:s,motor:Gt})}break;case"switch":l==="under_bed_lights"?e.lights.switch=d:l==="synchro_mode"?e.synchro=d:(l==="linak_automatic_drive"||l==="automatic_light")&&e.utility.push(d);break;case"light":e.lights.light=d;break;case"binary_sensor":l==="ble_connection"?e.connectivity=d:l==="sleeptracker_wind_down_running"?(e.massage.states??=[]).push(d):l==="reverie_pairlink_low_battery"?e.utility.push(d):l==="under_bed_lights"||l==="adjustable_lite_light"||l==="innova_light"||l==="sleeptracker_light_on"?e.lights.state=d:l.startsWith("bed_presence")&&e.presence.push(d);break;case"select":l==="motion_bed_active_module"||l.startsWith("okin_app_")?(e.utilitySelects??=[]).push(d):l==="reverie_stk_side"?(e.utilitySelects??=[]).push(d):l==="reverie_pairlink_massage_mode"||l==="reverie_pairlink_massage_rhythm"?(e.massage.selects??=[]).push(d):l==="light_timer"?e.lights.timer=d:l==="remacro_control_side"?e.controlSide=d:l==="starcode_color"||l==="vibradorm_app_mood_palette"||l==="vibradorm_app_mood_effect"||l==="vmatbasic_mood_palette"||l==="vmatbasic_mood_effect"?i().selects.push(d):l==="sleeptracker_wave_frequency"||/^sleeptracker_massage_(head_level|foot_level|pattern_option)$/.test(l)?(e.massage.selects??=[]).push(d):/^sleeptracker_(left|right)_(mode|curve)$/.test(l)?e.climate.selects.push(d):l==="vibradorm_app_massage_wave"?(e.massage.selects??=[]).push(d):l==="richmat_mh_motor_mode"||l==="richmat_mh_snore"?(e.utilitySelects??=[]).push(d):l.startsWith("richmat_mh_waist_")?(e.massage.selects??=[]).push(d):l==="massage_timer"||l==="starcode_abm5_4_massage_timer"||l==="ore_comfort_massage_timer"?e.massage.timer=d:/thermal|footwarming|foundation/.test(l)&&e.climate.selects.push(d);break;case"climate":e.climate.entities.push(d);break}}let b=[...c.keys()],y=[...Kt.filter(u=>c.has(u)),...b.filter(u=>!Kt.includes(u)).sort()];e.motors=y.map(u=>c.get(u)).filter(u=>u.cover||u.up||u.down||u.angle||u.position);let $=[...f.keys()];return e.presets=[...$t.filter(u=>f.has(u)),...$.filter(u=>!$t.includes(u)).sort()].map(u=>f.get(u)),e.memory=[..._.values()].filter(u=>u.goto||u.save).sort((u,d)=>u.slot-d.slot),e}function nt(n,s){return!s||!n?.entities?!1:Object.values(n.entities).some(t=>t.device_id===s&&t.platform===B&&(n.states[t.entity_id]?.attributes.bed_side==="both"||q(wt(t)).side==="both"))}function V(n,s){if(!s||!n?.devices)return[];let t=i=>{let o=n.devices[i];return(o?.name_by_user??o?.name??i).toLowerCase()},e=i=>{for(let o of Object.values(n.entities??{})){if(o.device_id!==i||o.platform!=="adjustable_bed")continue;let r=n.states[o.entity_id]?.attributes.bed_side??q(wt(o)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(n.devices).filter(i=>(i.parent_device_id??i.via_device_id)===s).map(i=>i.id).sort((i,o)=>e(i)-e(o)||t(i).localeCompare(t(o)))}function rt(n,s){if(!s||!n?.devices)return s;let t=n.devices[s]?.parent_device_id??n.devices[s]?.via_device_id;return t&&n.devices[t]&&V(n,t).length?t:s}function C(n){let s=n.lights;return n.motors.length===0&&!n.synchro&&!n.controlSide&&n.firmness.length===0&&n.presets.length===0&&n.memory.length===0&&!n.stop&&!n.connect&&!n.disconnect&&!n.connectivity&&!U(s)&&!s.state&&n.massage.buttons.length===0&&n.massage.numbers.length===0&&!n.massage.selects?.length&&!n.massage.states?.length&&!n.massage.timer&&n.climate.entities.length===0&&n.climate.selects.length===0&&n.climate.numbers.length===0&&n.utility.length===0&&!n.utilitySelects?.length}function U(n){return!!(n.light||n.switch||n.level||n.toggle||n.buttons?.length||n.cycle||n.timer||n.timerMinutes||n.timerToggle||n.mood?.toggle||n.mood?.selects.length||n.mood?.numbers.length||n.mood?.buttons?.length)}var kt="adjustable-bed-card",Wt={type:kt,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(n,s)=>{let t=n.entities[s];return t?.platform!==B||!t.device_id?null:{config:{type:`custom:${kt}`,device_id:t.device_id}}}};function Ee(n){let s=n.customCards??=[],t=s.findIndex(e=>e.type===kt);t===-1?s.push(Wt):s[t]=Wt}function at(n,s,t=window){let e=t.customElements;e.get(n)||e.define(n,s),e.whenDefined("home-assistant").then(()=>{let i=t.customElements;i!==e&&!i.get(n)&&i.define(n,s)})}typeof window<"u"&&Ee(window);var ct=globalThis,lt=ct.ShadowRoot&&(ct.ShadyCSS===void 0||ct.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,St=Symbol(),It=new WeakMap,Y=class{constructor(s,t,e){if(this._$cssResult$=!0,e!==St)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=t}get styleSheet(){let s=this.o,t=this.t;if(lt&&s===void 0){let e=t!==void 0&&t.length===1;e&&(s=It.get(t)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),e&&It.set(t,s))}return s}toString(){return this.cssText}},qt=n=>new Y(typeof n=="string"?n:n+"",void 0,St),J=(n,...s)=>{let t=n.length===1?n[0]:s.reduce((e,i,o)=>e+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[o+1],n[0]);return new Y(t,n,St)},Vt=(n,s)=>{if(lt)n.adoptedStyleSheets=s.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of s){let e=document.createElement("style"),i=ct.litNonce;i!==void 0&&e.setAttribute("nonce",i),e.textContent=t.cssText,n.appendChild(e)}},Et=lt?n=>n:n=>n instanceof CSSStyleSheet?(s=>{let t="";for(let e of s.cssRules)t+=e.cssText;return qt(t)})(n):n;var{is:Ae,defineProperty:Ce,getOwnPropertyDescriptor:Te,getOwnPropertyNames:Me,getOwnPropertySymbols:Pe,getPrototypeOf:Re}=Object,dt=globalThis,Yt=dt.trustedTypes,Be=Yt?Yt.emptyScript:"",ze=dt.reactiveElementPolyfillSupport,Q=(n,s)=>n,Z={toAttribute(n,s){switch(s){case Boolean:n=n?Be:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,s){let t=n;switch(s){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},pt=(n,s)=>!Ae(n,s),Jt={attribute:!0,type:String,converter:Z,reflect:!1,useDefault:!1,hasChanged:pt};Symbol.metadata??=Symbol("metadata"),dt.litPropertyMetadata??=new WeakMap;var A=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,t=Jt){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(s,t),!t.noAccessor){let e=Symbol(),i=this.getPropertyDescriptor(s,e,t);i!==void 0&&Ce(this.prototype,s,i)}}static getPropertyDescriptor(s,t,e){let{get:i,set:o}=Te(this.prototype,s)??{get(){return this[t]},set(r){this[t]=r}};return{get:i,set(r){let a=i?.call(this);o?.call(this,r),this.requestUpdate(s,a,e)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??Jt}static _$Ei(){if(this.hasOwnProperty(Q("elementProperties")))return;let s=Re(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(Q("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(Q("properties"))){let t=this.properties,e=[...Me(t),...Pe(t)];for(let i of e)this.createProperty(i,t[i])}let s=this[Symbol.metadata];if(s!==null){let t=litPropertyMetadata.get(s);if(t!==void 0)for(let[e,i]of t)this.elementProperties.set(e,i)}this._$Eh=new Map;for(let[t,e]of this.elementProperties){let i=this._$Eu(t,e);i!==void 0&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let t=[];if(Array.isArray(s)){let e=new Set(s.flat(1/0).reverse());for(let i of e)t.unshift(Et(i))}else s!==void 0&&t.push(Et(s));return t}static _$Eu(s,t){let e=t.attribute;return e===!1?void 0:typeof e=="string"?e:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,t=this.constructor.elementProperties;for(let e of t.keys())this.hasOwnProperty(e)&&(s.set(e,this[e]),delete this[e]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Vt(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,t,e){this._$AK(s,e)}_$ET(s,t){let e=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,e);if(i!==void 0&&e.reflect===!0){let o=(e.converter?.toAttribute!==void 0?e.converter:Z).toAttribute(t,e.type);this._$Em=s,o==null?this.removeAttribute(i):this.setAttribute(i,o),this._$Em=null}}_$AK(s,t){let e=this.constructor,i=e._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let o=e.getPropertyOptions(i),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:Z;this._$Em=i;let a=r.fromAttribute(t,o.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(s,t,e,i=!1,o){if(s!==void 0){let r=this.constructor;if(i===!1&&(o=this[s]),e??=r.getPropertyOptions(s),!((e.hasChanged??pt)(o,t)||e.useDefault&&e.reflect&&o===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,e))))return;this.C(s,t,e)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,t,{useDefault:e,reflect:i,wrapped:o},r){e&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??t??this[s]),o!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||e||(t=void 0),this._$AL.set(s,t)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,o]of this._$Ep)this[i]=o;this._$Ep=void 0}let e=this.constructor.elementProperties;if(e.size>0)for(let[i,o]of e){let{wrapped:r}=o,a=this[i];r!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,o,a)}}let s=!1,t=this._$AL;try{s=this.shouldUpdate(t),s?(this.willUpdate(t),this._$EO?.forEach(e=>e.hostUpdate?.()),this.update(t)):this._$EM()}catch(e){throw s=!1,this._$EM(),e}s&&this._$AE(t)}willUpdate(s){}_$AE(s){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(s){}firstUpdated(s){}};A.elementStyles=[],A.shadowRootOptions={mode:"open"},A[Q("elementProperties")]=new Map,A[Q("finalized")]=new Map,ze?.({ReactiveElement:A}),(dt.reactiveElementVersions??=[]).push("2.1.2");var Bt=globalThis,Qt=n=>n,ht=Bt.trustedTypes,Zt=ht?ht.createPolicy("lit-html",{createHTML:n=>n}):void 0,oe="$lit$",T=`lit$${Math.random().toFixed(9).slice(2)}$`,ne="?"+T,He=`<${ne}>`,O=document,tt=()=>O.createComment(""),et=n=>n===null||typeof n!="object"&&typeof n!="function",zt=Array.isArray,Oe=n=>zt(n)||typeof n?.[Symbol.iterator]=="function",At=`[ \t
\f\r]`,X=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Xt=/-->/g,te=/>/g,z=RegExp(`>|${At}(?:([^\\s"'>=/]+)(${At}*=${At}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),ee=/'/g,ie=/"/g,re=/^(?:script|style|textarea|title)$/i,Ht=n=>(s,...t)=>({_$litType$:n,strings:s,values:t}),g=Ht(1),gt=Ht(2),oi=Ht(3),L=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),se=new WeakMap,H=O.createTreeWalker(O,129);function ae(n,s){if(!zt(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Zt!==void 0?Zt.createHTML(s):s}var Le=(n,s)=>{let t=n.length-1,e=[],i,o=s===2?"<svg>":s===3?"<math>":"",r=X;for(let a=0;a<t;a++){let c=n[a],h,f,_=-1,v=0;for(;v<c.length&&(r.lastIndex=v,f=r.exec(c),f!==null);)v=r.lastIndex,r===X?f[1]==="!--"?r=Xt:f[1]!==void 0?r=te:f[2]!==void 0?(re.test(f[2])&&(i=RegExp("</"+f[2],"g")),r=z):f[3]!==void 0&&(r=z):r===z?f[0]===">"?(r=i??X,_=-1):f[1]===void 0?_=-2:(_=r.lastIndex-f[2].length,h=f[1],r=f[3]===void 0?z:f[3]==='"'?ie:ee):r===ie||r===ee?r=z:r===Xt||r===te?r=X:(r=z,i=void 0);let b=r===z&&n[a+1].startsWith("/>")?" ":"";o+=r===X?c+He:_>=0?(e.push(h),c.slice(0,_)+oe+c.slice(_)+T+b):c+T+(_===-2?a:b)}return[ae(n,o+(n[t]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),e]},it=class n{constructor({strings:s,_$litType$:t},e){let i;this.parts=[];let o=0,r=0,a=s.length-1,c=this.parts,[h,f]=Le(s,t);if(this.el=n.createElement(h,e),H.currentNode=this.el.content,t===2||t===3){let _=this.el.content.firstChild;_.replaceWith(..._.childNodes)}for(;(i=H.nextNode())!==null&&c.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let _ of i.getAttributeNames())if(_.endsWith(oe)){let v=f[r++],b=i.getAttribute(_).split(T),y=/([.?@])?(.*)/.exec(v);c.push({type:1,index:o,name:y[2],strings:b,ctor:y[1]==="."?Tt:y[1]==="?"?Mt:y[1]==="@"?Pt:K}),i.removeAttribute(_)}else _.startsWith(T)&&(c.push({type:6,index:o}),i.removeAttribute(_));if(re.test(i.tagName)){let _=i.textContent.split(T),v=_.length-1;if(v>0){i.textContent=ht?ht.emptyScript:"";for(let b=0;b<v;b++)i.append(_[b],tt()),H.nextNode(),c.push({type:2,index:++o});i.append(_[v],tt())}}}else if(i.nodeType===8)if(i.data===ne)c.push({type:2,index:o});else{let _=-1;for(;(_=i.data.indexOf(T,_+1))!==-1;)c.push({type:7,index:o}),_+=T.length-1}o++}}static createElement(s,t){let e=O.createElement("template");return e.innerHTML=s,e}};function G(n,s,t=n,e){if(s===L)return s;let i=e!==void 0?t._$Co?.[e]:t._$Cl,o=et(s)?void 0:s._$litDirective$;return i?.constructor!==o&&(i?._$AO?.(!1),o===void 0?i=void 0:(i=new o(n),i._$AT(n,t,e)),e!==void 0?(t._$Co??=[])[e]=i:t._$Cl=i),i!==void 0&&(s=G(n,i._$AS(n,s.values),i,e)),s}var Ct=class{constructor(s,t){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:t},parts:e}=this._$AD,i=(s?.creationScope??O).importNode(t,!0);H.currentNode=i;let o=H.nextNode(),r=0,a=0,c=e[0];for(;c!==void 0;){if(r===c.index){let h;c.type===2?h=new st(o,o.nextSibling,this,s):c.type===1?h=new c.ctor(o,c.name,c.strings,this,s):c.type===6&&(h=new Rt(o,this,s)),this._$AV.push(h),c=e[++a]}r!==c?.index&&(o=H.nextNode(),r++)}return H.currentNode=O,i}p(s){let t=0;for(let e of this._$AV)e!==void 0&&(e.strings!==void 0?(e._$AI(s,e,t),t+=e.strings.length-2):e._$AI(s[t])),t++}},st=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,t,e,i){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=s,this._$AB=t,this._$AM=e,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,t=this._$AM;return t!==void 0&&s?.nodeType===11&&(s=t.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,t=this){s=G(this,s,t),et(s)?s===p||s==null||s===""?(this._$AH!==p&&this._$AR(),this._$AH=p):s!==this._$AH&&s!==L&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):Oe(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==p&&et(this._$AH)?this._$AA.nextSibling.data=s:this.T(O.createTextNode(s)),this._$AH=s}$(s){let{values:t,_$litType$:e}=s,i=typeof e=="number"?this._$AC(s):(e.el===void 0&&(e.el=it.createElement(ae(e.h,e.h[0]),this.options)),e);if(this._$AH?._$AD===i)this._$AH.p(t);else{let o=new Ct(i,this),r=o.u(this.options);o.p(t),this.T(r),this._$AH=o}}_$AC(s){let t=se.get(s.strings);return t===void 0&&se.set(s.strings,t=new it(s)),t}k(s){zt(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,e,i=0;for(let o of s)i===t.length?t.push(e=new n(this.O(tt()),this.O(tt()),this,this.options)):e=t[i],e._$AI(o),i++;i<t.length&&(this._$AR(e&&e._$AB.nextSibling,i),t.length=i)}_$AR(s=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);s!==this._$AB;){let e=Qt(s).nextSibling;Qt(s).remove(),s=e}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},K=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,t,e,i,o){this.type=1,this._$AH=p,this._$AN=void 0,this.element=s,this.name=t,this._$AM=i,this.options=o,e.length>2||e[0]!==""||e[1]!==""?(this._$AH=Array(e.length-1).fill(new String),this.strings=e):this._$AH=p}_$AI(s,t=this,e,i){let o=this.strings,r=!1;if(o===void 0)s=G(this,s,t,0),r=!et(s)||s!==this._$AH&&s!==L,r&&(this._$AH=s);else{let a=s,c,h;for(s=o[0],c=0;c<o.length-1;c++)h=G(this,a[e+c],t,c),h===L&&(h=this._$AH[c]),r||=!et(h)||h!==this._$AH[c],h===p?s=p:s!==p&&(s+=(h??"")+o[c+1]),this._$AH[c]=h}r&&!i&&this.j(s)}j(s){s===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},Tt=class extends K{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===p?void 0:s}},Mt=class extends K{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==p)}},Pt=class extends K{constructor(s,t,e,i,o){super(s,t,e,i,o),this.type=5}_$AI(s,t=this){if((s=G(this,s,t,0)??p)===L)return;let e=this._$AH,i=s===p&&e!==p||s.capture!==e.capture||s.once!==e.once||s.passive!==e.passive,o=s!==p&&(e===p||i);i&&this.element.removeEventListener(this.name,this,e),o&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},Rt=class{constructor(s,t,e){this.element=s,this.type=6,this._$AN=void 0,this._$AM=t,this.options=e}get _$AU(){return this._$AM._$AU}_$AI(s){G(this,s)}};var je=Bt.litHtmlPolyfillSupport;je?.(it,st),(Bt.litHtmlVersions??=[]).push("3.3.3");var ce=(n,s,t)=>{let e=t?.renderBefore??s,i=e._$litPart$;if(i===void 0){let o=t?.renderBefore??null;e._$litPart$=i=new st(s.insertBefore(tt(),o),o,void 0,t??{})}return i._$AI(n),i};var Ot=globalThis,k=class extends A{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=ce(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return L}};k._$litElement$=!0,k.finalized=!0,Ot.litElementHydrateSupport?.({LitElement:k});var De=Ot.litElementPolyfillSupport;De?.({LitElement:k});(Ot.litElementVersions??=[]).push("4.2.2");var Ne={attribute:!0,type:String,converter:Z,reflect:!1,hasChanged:pt},Fe=(n=Ne,s,t)=>{let{kind:e,metadata:i}=t,o=globalThis.litPropertyMetadata.get(i);if(o===void 0&&globalThis.litPropertyMetadata.set(i,o=new Map),e==="setter"&&((n=Object.create(n)).wrapped=!0),o.set(t.name,n),e==="accessor"){let{name:r}=t;return{set(a){let c=s.get.call(this);s.set.call(this,a),this.requestUpdate(r,c,n,!0,a)},init(a){return a!==void 0&&this.C(r,void 0,n,a),a}}}if(e==="setter"){let{name:r}=t;return function(a){let c=this[r];s.call(this,a),this.requestUpdate(r,c,n,!0,a)}}throw Error("Unsupported decorator location: "+e)};function W(n){return(s,t)=>typeof t=="object"?Fe(n,s,t):((e,i,o)=>{let r=i.hasOwnProperty(o);return i.constructor.createProperty(o,e),r?Object.getOwnPropertyDescriptor(i,o):void 0})(n,s,t)}function M(n){return W({...n,state:!0,attribute:!1})}var j=n=>Math.max(0,Math.min(75,n));function Lt(n,s="theme"){let t=j(n.upper.angle??0),e=j(n.lower.angle??0),i=`rotate(${t} 150 70)`,o=`rotate(${-e} 150 70)`,r=a=>a.angle===void 0?"":`${a.label?`${a.label} `:""}${Math.round(j(a.angle))}\xB0`;return gt`
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
  `}function jt(n){let s=j(n.left.upper.angle??0),t=j(n.left.lower.angle??0),e=j(n.right.upper.angle??0),i=j(n.right.lower.angle??0),o=(r,a,c,h)=>gt`
    <g
      class="dual-bed-side dual-bed-side-${r} ${h?"is-moving":""}"
      fill=${`url(#abDual${r==="left"?"Left":"Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${`rotate(${-c} 150 70)`}
      >
        <rect class="dual-bed-surface" x="150" y="58" width="108" height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${`rotate(${a} 150 70)`}
      >
        <rect class="dual-bed-surface" x="42" y="58" width="108" height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
    </g>
  `;return gt`
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
      ${o("right",e,i,n.right.moving)}
      ${o("left",s,t,n.left.moving)}
    </svg>
  `}function Dt(n){let s=n.find(e=>e.key==="back"||e.key==="head"),t=n.find(e=>e.key==="legs"||e.key==="feet");return s&&t?{upper:s,lower:t}:void 0}function le(n,s){let t=n.motors.filter(e=>{let i=e.angle??e.position;return s.states[i??""]?.attributes.unit_of_measurement==="\xB0"});return Dt(t)!==void 0}function Nt(n,s,t){if(s.timedMove)return n?.callService("adjustable_bed","timed_move",{device_id:s.timedMove.deviceId,...s.timedMove.side?{side:s.timedMove.side}:{},motor:s.timedMove.motor,direction:t,duration_ms:1e3});if(s.cover)return n?.callService("cover",t==="up"?"open_cover":"close_cover",{entity_id:s.cover});let e=t==="up"?s.up:s.down;return e?n?.callService("button","press",{entity_id:e}):void 0}function de(n,s,t){Nt(n,s,t)?.catch(()=>{})}function pe(n,s,t,e){let i=()=>e(),o=()=>{t()&&e()};n.addEventListener("blur",i),s.addEventListener("visibilitychange",o);let r=!0;return()=>{r&&(r=!1,n.removeEventListener("blur",i),s.removeEventListener("visibilitychange",o))}}var mt=class{constructor(s){this.actions=s;this._key=null;this._motor=null;this._mode=null;this._cover=null;this._stop=null;this._scopeStops=[];this._remainingStops=[];this._stopTargetGenerations=new Map;this._pointerId=null;this._keyboardKey=null;this._generation=0}get heldKey(){return this._key}start(s,t,e,i,o=i?[i]:[],r=[],a=null){this._key===null&&(this._key=s.key,this._motor=Object.freeze({...s,...s.timedMove?{timedMove:Object.freeze({...s.timedMove})}:{}}),this._mode=s.cover?"cover":"bed",this._cover=s.cover??null,this._stop=i??null,this._scopeStops=[...new Set([...o,...i?[i]:[],...s.cover?[s.cover]:[]])],this._remainingStops=[...new Set(r)],this.claimStopScope(this._scopeStops),this._pointerId=e,this._keyboardKey=a,this._repeat(s,t,++this._generation))}claimStopScope(s){for(let t of new Set(s))this._stopTargetGenerations.set(t,(this._stopTargetGenerations.get(t)??0)+1)}async _repeat(s,t,e){let i=this._motor;if(i)for(;e===this._generation;)try{let o=this.actions.pulse(i,t);if(!o)return;this._pulseInFlight=o;try{await o}finally{this._pulseInFlight===o&&(this._pulseInFlight=void 0)}}catch{return}}endFromPointer(s,t,e,i){this._pointerId===null||t!==this._pointerId||e&&(i!==void 0&&this._stop!==i||this.end(s,i))}endActiveFromPointer(s,t){!this._motor||this._pointerId===null||this.endFromPointer(this._motor,s,t)}endKeyboard(s,t,e){this._pointerId!==null||!this._motor||s&&s.key!==this._key||t!==void 0&&this._stop!==t||e!==void 0&&this._keyboardKey!==null&&this._keyboardKey!==e||this.end(this._motor)}end(s,t){if(t!==void 0&&this._stop!==t)return;let e=this._mode,i=this._cover,o=this._stop??void 0;if(this.cancel(s)){if(e==="cover"&&i){this.actions.stopCover(i,o);return}this.actions.stopBed(o)}}cancel(s){return!s||this._key!==s.key?!1:(this._reset(),!0)}stopAll(s,t,e){let i=s??this._stop??void 0,o=[...new Set([...t??(i?[i]:this._scopeStops),...i?[i]:[]])],r=e===void 0||e===this._key||i===this._cover,a=this._key!==null&&r&&(o.length===0||this._scopeStops.some(_=>o.includes(_))),c=a?this._remainingStops.filter(_=>!o.includes(_)):[],h=a?this._pulseInFlight:void 0,f=new Map(c.map(_=>[_,this._stopTargetGenerations.get(_)??0]));if(a&&this._reset(),this.actions.stopBed(i),c.length>0){let _=()=>{for(let v of c)this._stopTargetGenerations.get(v)===f.get(v)&&this.actions.stopBed(v)};h?h.then(_,_):_()}}abandon(){let s=this._key!==null,t=this._mode,e=this._cover,i=this._stop??void 0;this._reset(),s&&(t==="cover"&&e?this.actions.stopCover(e,i):this.actions.stopBed(i))}releaseOnFocusLoss(){this.abandon()}cancelForStopScope(s){return this._key===null||!this._scopeStops.some(t=>s.includes(t))&&(this._stop===null||!s.includes(this._stop))&&(this._cover===null||!s.includes(this._cover))?!1:(this._reset(),!0)}_reset(){this._key=null,this._motor=null,this._mode=null,this._cover=null,this._stop=null,this._scopeStops=[],this._remainingStops=[],this._pointerId=null,this._keyboardKey=null,this._pulseInFlight=void 0,this._generation++}};function _t(n,s,t,e){n.stopAll(s,t??(s?[s]:void 0),e)}var he={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both"};var ge={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge"};var D={en:he,nb:ge};function Ke(n){let s=(n?.locale?.language||n?.language||"en").toLowerCase(),t=s.split("-")[0];return D[s]?D[s]:D[t]?D[t]:t==="nn"||t==="no"?D.nb:D.en}function m(n,s,t){let i=Ke(n)[s]??D.en[s]??s;if(t)for(let[o,r]of Object.entries(t))i=i.replace(`{${o}}`,r);return i}var ue=["glance","quick","controls"];function me(n,s){let t={...n,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:s==="glance"?"names":"angles",show_side_selector:!0,show_motors:s==="controls",show_lighting:!1,show_connection:!1,animate:!0};return s==="glance"?t.compact_actions=[]:delete t.compact_actions,t}function Ft(n,s){return[...s.presets,...s.memory.flatMap(t=>t.goto?[t.goto]:[])].flatMap(t=>{let e=n.entities[t]?.translation_key;return e?[{key:q(e).key,entityId:t}]:[]})}function ft(n,s,t){let e=Ft(n,s);if(t){let r=new Map(e.map(a=>[a.key,a]));return[...new Set(t)].flatMap(a=>{let c=r.get(a);return c?[c]:[]})}let i=e.find(r=>r.key==="preset_flat"),o=e.find(r=>r.key.startsWith("preset_memory_"))??e.find(r=>r!==i);return[i,o].filter(r=>r!==void 0)}function vt(n){return n.stop?[n.stop]:n.motors.flatMap(s=>s.cover?[s.cover]:[])}function bt(n){if(!(!n||!n.startsWith("/")||/^\/[/\\]/.test(n)||/[\\\s]/.test(n)))return n}function yt(n,s){let t=rt(n,s),e=V(n,t);return t&&e.length?[{key:"both",label:m(n,"card.both_sides"),bed:x(n,t)},...e.map(i=>({key:i,label:n.devices[i]?.name_by_user??n.devices[i]?.name??i,bed:x(n,i)}))]:nt(n,s)?["both","left","right"].map(i=>({key:i,label:m(n,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:x(n,s,i)})):[{key:"both",label:m(n,"card.both_sides"),bed:x(n,s)}]}var _e="4.2.4";function fe(n,s){return{graphic:le(n,s),motors:n.motors.some(t=>t.cover||t.up||t.down)||!!n.stop||!!n.synchro,firmness:n.firmness.length>0,presets:n.presets.length>0,memory:n.memory.length>0,lighting:U(n.lights)||!!n.lights.state,massage:n.massage.buttons.length>0||n.massage.numbers.length>0||!!n.massage.states?.length||!!n.massage.selects?.length||!!n.massage.timer,utility:n.utility.length>0,climate:n.climate.entities.length>0||n.climate.selects.length>0||n.climate.numbers.length>0,connection:!!(n.connect||n.disconnect)}}var We="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",Ie="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",qe=(n,s)=>n.length===s.length&&n.every((t,e)=>t===s[e]),I=class extends k{constructor(){super(...arguments);this._computeLabel=t=>m(this.hass,`editor.${t.name}`)}setConfig(t){this._config=t}_bed(){let t=this._config?.device_id;if(!this.hass||!t)return;let e=yt(this.hass,t).map(r=>r.bed),i=e[0];if(!i)return;let o=new Map;for(let r of e)for(let a of r.memory){let c=o.get(a.slot);o.set(a.slot,{slot:a.slot,goto:c?.goto??a.goto,save:c?.save??a.save})}return{...i,memory:[...o.values()].sort((r,a)=>r.slot-a.slot)}}_presentKeys(t){let e=this.hass?yt(this.hass,this._config?.device_id).map(i=>i.bed):[t];return F.filter(i=>e.some(o=>fe(o,this.hass)[i]))}_orderedKeys(t){let e=this._presentKeys(t),o=(this._config?.section_order??[]).filter(a=>e.includes(a)),r=e.filter(a=>!o.includes(a));return[...o,...r]}_memorySlots(t){return t?t.memory.map(e=>e.slot):[]}_slotLabel(t){let e=t.goto??t.save,i=e&&this.hass?.states[e]?.attributes.friendly_name||`Memory ${t.slot}`,o=e&&this.hass?.entities[e]?.device_id,r=o?this.hass?.devices[o]:void 0,a=r?.name_by_user||r?.name;return a&&i.startsWith(`${a} `)?i.slice(a.length+1):i}_emit(t){t.type=t.type??"custom:adjustable-bed-card",t.name||delete t.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(t){t.stopPropagation();let e=t.detail.value,i=this._cfg;i.device_id!==e.device_id&&delete i.default_target,i.device_id=e.device_id||void 0,e.name?i.name=e.name:delete i.name,this._emit(i)}_toggleSection(t,e){let i=this._cfg;e?delete i[`show_${t}`]:i[`show_${t}`]=!1,this._emit(i)}_moveSection(t,e,i){let o=this._orderedKeys(t),r=o.indexOf(e),a=r+i;if(r<0||a<0||a>=o.length)return;[o[r],o[a]]=[o[a],o[r]];let c=this._cfg;qe(o,this._presentKeys(t))?delete c.section_order:c.section_order=o,this._emit(c)}_setMemorySave(t){let e=this._cfg;t?delete e.memory_save:e.memory_save=!1,this._emit(e)}_slotChecked(t){let e=this._config?.memory_slots;return!e||!e.length||e.map(Number).includes(t)}_toggleSlot(t,e,i){let o=this._memorySlots(t),r=this._config?.memory_slots,a=r&&r.length?r.map(Number):[...o];i?a.includes(e)||a.push(e):a=a.filter(h=>h!==e),a.sort((h,f)=>h-f);let c=this._cfg;a.length===o.length?delete c.memory_slots:c.memory_slots=a,this._emit(c)}_sectionsGroup(t){let e=this._orderedKeys(t);return e.length?g`
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.sections")}</div>
        ${e.map((i,o)=>{let r=this._config?.[`show_${i}`]!==!1;return g`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${o===0}
                  @click=${()=>this._moveSection(t,i,-1)}
                  title=${m(this.hass,"editor.move_up")}
                  aria-label=${m(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${We}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${o===e.length-1}
                  @click=${()=>this._moveSection(t,i,1)}
                  title=${m(this.hass,"editor.move_down")}
                  aria-label=${m(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Ie}></path></svg>
                </button>
              </div>
              <span class="label">${m(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${r}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:p}_memoryGroup(t){if(!(t.memory.length>0&&this._config?.show_memory!==!1))return p;let i=t.memory.some(r=>r.save),o=t.memory.length>1;return!i&&!o?p:g`
      <div class="group">
        <div class="group-title">
          ${m(this.hass,"editor.memory_group")}
        </div>
        ${i?g`<div class="row">
                <span class="label">${m(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:p}
        ${o?g`<div class="sub">
                <div class="sub-label">
                  ${m(this.hass,"editor.memory_slots")}
                </div>
                ${t.memory.map(r=>g`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${a=>this._toggleSlot(t,r.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(r)}</span>
                    </label>
                  `)}
              </div>`:p}
      </div>
    `}_setOption(t,e){this._emit({...this._cfg,[t]:e})}_compactToggle(t,e){return g`<div class="row"><span class="label">${m(this.hass,t==="show_connection"?"editor.compact_connection":`editor.${t}`)}</span>
      <ha-switch .checked=${this._config?.[t]??e}
        @change=${i=>this._setOption(t,i.target.checked)}></ha-switch>
    </div>`}_compactGroup(){let t=this._config,e=yt(this.hass,t.device_id),i=e.find(c=>c.key===(t.default_target??"both")),o=e.flatMap(c=>Ft(this.hass,c.bed)).filter((c,h,f)=>f.findIndex(_=>_.key===c.key)===h),r=t.compact_actions??(i?ft(this.hass,i.bed).map(c=>c.key):[]),a=[...r.filter(c=>o.some(h=>h.key===c)),...o.map(c=>c.key).filter(c=>!r.includes(c))];return g`
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        <label class="row"><span class="label">${m(this.hass,"editor.compact_labels")}</span>
          <select .value=${t.compact_labels??"angles"}
            @change=${c=>this._setOption("compact_labels",c.target.value)}>
            ${["angles","names","none"].map(c=>g`
              <option value=${c}>${m(this.hass,`editor.labels_${c}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        <label class="row path-row"><span class="label">${m(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${t.navigation_path??""} placeholder="/dashboard/bed"
            @change=${c=>this._setOption("navigation_path",c.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${m(this.hass,"editor.compact_controls")}</div>
        ${e.length>1||!i?g`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${m(this.hass,"editor.default_target")}</span>
            <select .value=${t.default_target??"both"}
              @change=${c=>this._setOption("default_target",c.target.value)}>
              ${i?p:g`<option value=${t.default_target}>${m(this.hass,"compact.target_missing")}</option>`}
              ${e.map(c=>g`<option value=${c.key}>${c.label}</option>`)}
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
        ${a.map(c=>{let h=o.find(y=>y.key===c),f=r.includes(c),_=r.indexOf(c),v=y=>{let $=[...r];[$[_],$[_+y]]=[$[_+y],$[_]],this._setOption("compact_actions",$)},b=this.hass.states[h.entityId];return g`<div class="row">
            <ha-checkbox .checked=${f} @change=${y=>this._setOption("compact_actions",y.target.checked?[...r,c]:r.filter($=>$!==c))}></ha-checkbox>
            <span class="label">${b?.attributes.friendly_name??c}</span>
            <button class="icon-btn" ?disabled=${!f||_===0}
              aria-label=${m(this.hass,"editor.move_up")} @click=${()=>v(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!f||_===r.length-1}
              aria-label=${m(this.hass,"editor.move_down")} @click=${()=>v(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return g`<div class="group">
      <label class="row"><span class="label">${m(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${t=>this._setOption("layout",t.target.value)}>
          <option value="full">${m(this.hass,"editor.layout_full")}</option>
          <option value="compact">${m(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${m(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${ue.map(t=>g`
        <button @click=${()=>this._emit({...me(this._config,t)})}>
          ${m(this.hass,`editor.recipe_${t}`)}
        </button>`)}</div>
    </div>`}render(){if(!this.hass||!this._config)return p;let t=this._bed();return g`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():g`
        ${t?this._sectionsGroup(t):p}
        ${t?this._memoryGroup(t):p}
      `}
    `}};I.styles=J`
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
  `,w([W({attribute:!1})],I.prototype,"hass",2),w([M()],I.prototype,"_config",2);at("adjustable-bed-card-editor",I);var Ve=new Set(["back","legs","head","feet"]),S=class extends k{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._watched=[];this._compactStopTargets=new Map;this._hold=new mt({pulse:(t,e)=>Nt(this.hass,t,e),stopCover:(t,e)=>this._stopCompactTarget(t,e??t),stopBed:t=>{t&&this._stopCompactTarget(t)}});this._focusLossCleanup=null;this._windowPointerEnd=t=>{this._hold.endActiveFromPointer(t.pointerId,t.type==="pointercancel"||t.button===0)};this._windowKeyUp=t=>{(t.key==="Enter"||t.key===" ")&&this._hold.endKeyboard(void 0,void 0,t.key)};this._navigate=()=>{let t=bt(this._config?.navigation_path);t&&(this._hold.abandon(),history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))}}connectedCallback(){super.connectedCallback(),window.addEventListener("pointerup",this._windowPointerEnd),window.addEventListener("pointercancel",this._windowPointerEnd),window.addEventListener("keyup",this._windowKeyUp),this._focusLossCleanup=pe(window,document,()=>document.visibilityState==="hidden",()=>this._hold.releaseOnFocusLoss())}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(t){return{type:"custom:adjustable-bed-card",device_id:t?Object.values(t.entities).find(i=>i.platform===B)?.device_id:void 0}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._config&&(this._compactStopTargets.size>0?this._stopCompact():this._hold.abandon()),(t.device_id!==this._config?.device_id||t.default_target!==this._config?.default_target)&&(this._activePairedPane=t.default_target??"both"),this._config=t}getCardSize(){if(this._config?.layout!=="compact")return 8;let t=this._config;return Math.ceil((24+(t.show_header!==!1?36:0)+(t.show_graphic!==!1?150:0)+(t.compact_labels!=="none"?40:0)+(t.compact_actions?.length===0?0:110)+(t.show_motors===!0?180:0)+(t.show_lighting===!0?70:0)+(t.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){window.removeEventListener("pointerup",this._windowPointerEnd),window.removeEventListener("pointercancel",this._windowPointerEnd),window.removeEventListener("keyup",this._windowKeyUp),this._focusLossCleanup?.(),this._focusLossCleanup=null,super.disconnectedCallback(),this._hold.abandon()}shouldUpdate(t){if(t.has("_config")||t.has("_saveModeFor")||t.has("_activePairedPane")||t.has("_synchronizingTo")||t.has("_synchronizationFailed")||!t.has("hass")||!this.hass)return!0;let e=t.get("hass");if(!e||e.entities!==this.hass.entities||e.devices!==this.hass.devices)return!0;for(let i of this._watched)if(e.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return p;if(!this._config.device_id)return this._notice("card.no_device");let t=rt(this.hass,this._config.device_id),e=V(this.hass,t);if(t&&e.length)return this._renderPaired(t,e);if(this._config.device_id&&nt(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=x(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),C(i)?this._notice("card.no_entities"):this._config.layout==="compact"?this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:i}],!1):g`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(t,e="theme",i,o,r){let a=this._config,c={graphic:()=>a.show_graphic!==!1?i??this._graphic(t,e):p,motors:()=>a.show_motors!==!1?this._motors(t,o,r):p,firmness:()=>a.show_firmness!==!1?this._firmness(t):p,presets:()=>a.show_presets!==!1?this._presets(t):p,memory:()=>a.show_memory!==!1?this._memory(t):p,lighting:()=>a.show_lighting!==!1?this._lighting(t):p,massage:()=>a.show_massage!==!1?this._massage(t):p,utility:()=>a.show_utility!==!1?this._utility(t):p,climate:()=>a.show_climate!==!1?this._climate(t):p,connection:()=>a.show_connection!==!1?this._connection(t):p};return this._orderedSections().map(h=>c[h]?.()??p)}_renderPaired(t,e){let i=this.hass,o=x(i,t),r=e.map((_,v)=>({key:_,label:this._deviceLabel(_),bed:x(i,_),graphicTone:v===0?"left":"right",synchronizationTarget:{deviceId:_}})),a=r.flatMap(_=>_.bed.stop?[_.bed.stop]:[]),c=o.stop,h=[...new Set([...c?[c]:[],...a])],f=[{key:"both",label:m(i,"card.both_sides"),bed:o,stopScope:h,remainingStopIds:a},...r.map(_=>({..._,stopScope:_.bed.stop?[_.bed.stop]:[]}))];return this._watched=[o,...r.map(_=>_.bed)].flatMap(_=>this._collectWatched(_)),C(o)&&r.every(_=>C(_.bed))?this._notice("card.no_entities"):this._renderPairedCard(t,f)}_renderSingleAddressPaired(t){let e=this.hass,i={both:x(e,t,"both"),left:x(e,t,"left"),right:x(e,t,"right")},o=[i.left.stop,i.right.stop].filter(r=>r!==void 0);return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>C(r))?this._notice("card.no_entities"):this._renderPairedCard(t,[{key:"both",label:m(e,"card.both_sides"),bed:i.both,stopScope:[...new Set([i.both.stop,...o].filter(r=>r!==void 0))],remainingStopIds:o},{key:"left",label:m(e,"card.left_side"),bed:i.left,graphicTone:"left",stopScope:i.left.stop?[i.left.stop]:[],synchronizationTarget:{deviceId:t,side:"left"}},{key:"right",label:m(e,"card.right_side"),bed:i.right,graphicTone:"right",stopScope:i.right.stop?[i.right.stop]:[],synchronizationTarget:{deviceId:t,side:"right"}}])}_renderPairedCard(t,e){if(this._config?.layout==="compact")return this._renderCompact(t,e,!0);let i=e.filter(c=>!C(c.bed)),o=i.find(c=>c.key===this._activePairedPane)??i[0],r=i.filter(c=>c.key!=="both"),a=o.key==="both";return g`
      <ha-card class="paired-card">
        ${this._header(o.bed,t)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(c=>g`
              <button
                class="pane-tab side-${c.graphicTone??"theme"} ${c.key===o.key?"active":""}"
                role="tab"
                aria-selected=${c.key===o.key?"true":"false"}
                @click=${()=>this._selectPairedPane(c.key)}
              >
                ${c.graphicTone?g`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span>${c.key==="both"?m(this.hass,"card.both"):c.label}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${o.label}>
          ${this._renderSections(o.bed,o.graphicTone,a?this._pairedOverview(r):void 0,o.stopScope,o.remainingStopIds)}
          ${a&&this._config?.show_lighting!==!1?this._combinedLighting(o.bed,r):p}
          ${a&&this._config?.show_connection!==!1?this._combinedBluetooth(r):p}
        </div>
      </ha-card>
    `}_renderCompact(t,e,i){let o=this._config,r=e.find(u=>u.key===this._activePairedPane),a=r?.bed,c=a?ft(this.hass,a,o.compact_actions):[],h=o.show_motors===!0&&a?a.motors.filter(u=>u.cover||u.up||u.down||u.position):[],f=c.length>0||h.length>0||o.show_lighting===!0,_=o.compact_actions?.length!==0||o.show_motors===!0||o.show_lighting===!0,v=i?e.filter(u=>u.key!=="both"):e,b=!!a&&vt(a).length>0,y=c.length>0||h.length>0,$=bt(o.navigation_path);return g`
      <ha-card class="compact-card ${_?"":"compact-glance"} ${o.animate===!1?"no-animation":""}">
        ${o.show_header!==!1?g`
          <div class="compact-header">
            <span class="title">${this._title(t)}</span>
            ${$?g`<button class="compact-open" @click=${this._navigate}
              aria-label=${m(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:p}
          </div>`:p}
        ${i&&_?o.show_side_selector!==!1?g`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${e.filter(u=>!C(u.bed)).length}`}
            aria-label=${m(this.hass,"compact.target")}>
            ${e.filter(u=>!C(u.bed)).map(u=>g`
              <button class="pane-tab side-${u.graphicTone??"theme"} ${u.key===r?.key?"active":""}"
                aria-pressed=${u.key===r?.key?"true":"false"}
                title=${u.label}
                @click=${()=>this._selectPairedPane(u.key)}>
                ${u.graphicTone?g`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span class="compact-tab-label">${u.key==="both"?m(this.hass,"card.both"):u.label}</span>
              </button>`)}
          </div>`:g`<div class="compact-target">
            ${m(this.hass,"compact.target")}: ${r?.label??m(this.hass,"compact.target_missing")}
          </div>`:p}
        ${o.show_graphic!==!1?this._compactGraphic(v):p}
        ${this._compactReadouts(v)}
        ${!r&&_?g`<div class="hint" role="status">
          ${m(this.hass,"compact.target_missing")}</div>`:p}
        ${h.length?g`<div class="rows compact-motors">
          ${h.map(u=>u.cover||u.up||u.down?this._motorRow(u,a?.stop,!0,r?.stopScope,r?.remainingStopIds):this._moreInfoRow(u.position))}
        </div>`:p}
        ${c.length||y||this._compactStopTargets.size?g`
          <div class="tiles compact-actions">
            ${c.map(({entityId:u})=>g`<button class="tile"
              ?disabled=${!b||!this._available(u)}
              @click=${()=>this._compactRecall(u,a)}>
              ${this._icon(u)}<span class="tile-label">${this._name(u)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!b&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(a)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${m(this.hass,"action.stop")}</span>
            </button>
          </div>`:p}
        ${o.show_lighting===!0&&a?g`
          ${this._lighting(a)}
          ${i&&r?.key==="both"?this._combinedLighting(a,v):p}
        `:p}
        ${o.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(v):g`<div class="compact-connections">
          ${v.map(u=>{let d=this._connectionStatus(u.bed);return d?g`<span>${this._connectionDot(u.bed)}
              ${u.label}: ${m(this.hass,`status.${d}`)}</span>`:p})}
        </div>`:p}
        ${!f&&o.show_graphic===!1&&o.compact_labels==="none"&&o.show_header===!1&&o.show_connection!==!0?g`<div class="hint">${this._title(t)}</div>`:p}
      </ha-card>`}_compactGraphic(t){let e=t.map(h=>this._graphicState(h.bed)),i=e[0],o=e[1],r=e.length>0&&e.every(h=>h!==void 0),a=t.map((h,f)=>`${h.label}: ${e[f]?this._positionSummary(e[f]):m(this.hass,"compact.no_position")}`).join(". "),c=r&&i?o?jt({left:i,right:o}):Lt({...i,upper:{angle:i.upper.angle},lower:{angle:i.lower.angle}}):g`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${m(this.hass,"compact.no_position")}</span></div>`;return bt(this._config?.navigation_path)?g`<button class="compact-graphic" @click=${this._navigate}
          aria-label="${m(this.hass,"compact.open")}. ${a}">${c}</button>`:g`<div class="compact-graphic" role="img" aria-label=${a}>${c}</div>`}_compactReadouts(t){let e=this._config?.compact_labels??"angles";return e==="none"?p:g`<div class="compact-readouts ${e==="names"?"compact-names":""}">
      ${t.map(i=>g`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span aria-label=${i.label}>${e==="angles"&&t.length>1?[...i.label][0]:i.label}</span>
        </span>
        ${e==="angles"?g`<span class="compact-position"
          title=${i.bed.motors.map(o=>`${this._motorName(o)} ${this._readout(o)??"?"}`).join(" \xB7 ")}
        >${i.bed.motors.filter(o=>o.angle||o.position||o.cover).map(o=>this._readout(o)??"?").join(" / ")||m(this.hass,"compact.no_position")}</span>`:p}
      </div>`)}
    </div>`}_available(t){let e=this._state(t)?.state;return e!==void 0&&e!=="unavailable"}_compactRecall(t,e){this._hold.abandon(),vt(e).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(t),this.requestUpdate()}_stopCompact(t){let e=[...new Set([...t?vt(t):[],...this._compactStopTargets.keys()])];this._hold.cancelForStopScope(e);for(let i of e)this._compactStopTargets.has(i)||this._compactStopTargets.set(i,Symbol());for(let i of this._compactStopTargets.keys())this._stopCompactTarget(i);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(t,e=t){let i=this._compactStopTargets.get(e),o=t.startsWith("cover.");this.hass?.callService(o?"cover":"button",o?"stop_cover":"press",{entity_id:t}).then(()=>{i!==void 0&&this._compactStopTargets.get(e)===i&&(this._compactStopTargets.delete(e),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(t){this._activePairedPane!==t&&(this._activePairedPane=t,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(t){if(!t.connectivity)return;let e=this._state(t.connectivity);return e?.attributes?.state_detail==="connecting"?"connecting":e?.state==="on"?"connected":e?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(t){let e=this._connectionStatus(t);return e?g`<span
      class="connection-dot ${e}"
      title=${m(this.hass,`status.${e}`)}
    ></span>`:p}_pairedOverview(t){let e=t.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(e.length<2)return p;let[i,o]=e;return g`
      <div class="graphic dual-graphic">
        ${jt({left:i.graphic,right:o.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,o].map(({pane:r,graphic:a},c)=>g`
            <div class="dual-readout side-${c===0?"left":"right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${r.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(a)}
              </span>
            </div>
          `)}
      </div>
      ${this._synchronizeSelector(i.pane,o.pane)}
    `}_synchronizeSelector(t,e){if(!t.synchronizationTarget||!e.synchronizationTarget)return p;let i=this._synchronizationPlan(t.bed,e.bed),o=this._synchronizationPlan(e.bed,t.bed);if(i.length===0&&o.length===0)return p;let r=this._synchronizingTo!==void 0;return g`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${m(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${m(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"left")}
          >
            ${this._synchronizingTo==="left"?g`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:g`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${m(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||o.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"right")}
          >
            ${this._synchronizingTo==="right"?g`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:g`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?g`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${m(this.hass,"sync.incomplete")}</span>
          </div>`:p}
    `}_synchronizationPlan(t,e){let i=new Map(e.motors.map(a=>[a.key,a])),o=t.motors.filter(a=>Ve.has(a.key)&&i.has(a.key)&&this._hasPositionFeedback(a)&&this._hasPositionFeedback(i.get(a.key)));if(o.length===0)return[];let r=o.map(a=>({motor:a.key,position:this._angle(a)}));return r.some(a=>a.position===void 0)||o.some(a=>this._angle(i.get(a.key))===void 0)?[]:r}_hasPositionFeedback(t){return t.angle!==void 0||t.position!==void 0}async _synchronizePositions(t,e,i){if(this._synchronizingTo||!this.hass)return;let o=i==="left"?t:e,r=i==="left"?e:t,a=r.synchronizationTarget;if(!a)return;let c=this._synchronizationPlan(o.bed,r.bed);if(c.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(B,"set_positions",{device_id:[a.deviceId],positions:c,...a.side?{side:a.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(t){return(t.upperMotor===t.lowerMotor?[t.upperMotor]:[t.upperMotor,t.lowerMotor]).map(i=>{let o=this._readout(i);return o?`${this._motorName(i)} ${o}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(t,e){if(this._hasLighting(t))return p;let i=e.map(f=>this._mainLight(f.bed)).filter(f=>f!==void 0);if(i.length===0)return p;let o=i.filter(f=>this._state(f)?.state==="on").length,r=o===i.length,a=o>0,c=r?"combined.on":a?"combined.mixed":"combined.off",h=m(this.hass,"combined.lights");return g`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${a?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${h}</span>
          <span class="secondary">${m(this.hass,c)}</span>
        </div>
        <button
          class="toggle ${a?"on":""} ${a&&!r?"mixed":""}"
          role="switch"
          aria-label=${h}
          aria-checked=${r?"true":"false"}
          @click=${()=>this._setEntities(i,!r)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_combinedBluetooth(t){let e=t.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return e.length===0?p:g`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${e.map(({pane:i,entityId:o})=>{let r=this._connectionStatus(i.bed),c=this._state(o)?.attributes.rssi;return g`
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
                  ${m(this.hass,`status.${r}`)}${typeof c=="number"?` \xB7 ${c} dBm`:""}
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
    `}_mainLight(t){return t.lights.light??t.lights.switch}_hasLighting(t){return U(t.lights)}_deviceLabel(t){let e=this.hass?.devices[t];return e?.name_by_user??e?.name??t}_orderedSections(){let t=this._config?.section_order;if(!t?.length)return[...F];let e=new Set(F),i=t.filter(r=>e.has(r)),o=F.filter(r=>!i.includes(r));return[...i,...o]}_header(t,e){let i=this._connectionStatus(t),o={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return g`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(e)}</span>
        ${i===void 0?p:g`
                <button
                  class="conn ${o[i].cls}"
                  @click=${()=>this._moreInfo(t.connectivity)}
                  title=${m(this.hass,o[i].key)}
                >
                  <ha-icon icon=${o[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(t,e="theme"){let i=this._graphicState(t);return i?g`
      <div class="graphic">
        ${Lt(i,e)}
      </div>
    `:p}_graphicState(t){let e=t.motors.filter(c=>{let h=c.angle??c.position;return h!==void 0&&this._state(h)?.attributes.unit_of_measurement==="\xB0"});if(e.length===0||e.some(c=>this._angle(c)===void 0))return;let i=Dt(e);if(!i)return;let{upper:o,lower:r}=i,a=t.motors.some(c=>{let h=c.cover?this._state(c.cover)?.state:void 0;return h==="opening"||h==="closing"});return{upperMotor:o,lowerMotor:r,upper:{label:this._motorName(o),angle:this._angle(o)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:a}}_motors(t,e,i){let o=e??(t.stop?[t.stop]:[]),r=t.motors.filter(h=>h.cover||h.up||h.down),a=t.motors.filter(h=>h.position&&!h.cover&&!h.up&&!h.down);if(r.length===0&&a.length===0&&!t.synchro&&!t.controlSide&&!t.stop)return p;let c=r.length>0||a.length>0||!!t.synchro||!!t.controlSide;return g`
      ${c?this._heading("section.position"):p}
      ${t.controlSide?this._moreInfoRow(t.controlSide):p}
      ${t.synchro?this._toggleRow(t.synchro):p}
      ${r.length?g`<div class="rows">
              ${r.map(h=>this._motorRow(h,t.stop,!1,o,i))}
            </div>`:p}
      ${a.length?g`<div class="rows">
              ${a.map(h=>this._moreInfoRow(h.position))}
            </div>`:p}
      ${t.stop?g`<button class="stop-all" @click=${()=>_t(this._hold,t.stop,o)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${m(this.hass,"action.stop_all")}</span>
            </button>`:p}
    `}_firmness(t){return t.firmness.length===0?p:g`
      ${this._heading("section.firmness")}
      <div class="rows">${t.firmness.map(e=>this._moreInfoRow(e))}</div>
    `}_motorRow(t,e,i=!1,o,r){let a=this._readout(t),c=!!t.cover||!!e,h=g`
      <span>${this._motorName(t)}</span>
      ${a&&!i?g`<span class="readout">${a}</span>`:p}
    `;return g`
      <div class="row">
        ${t.position?g`<button
              class="row-label position-label"
              aria-label=${this._name(t.position)}
              @click=${()=>this._moreInfo(t.position)}
            >${h}</button>`:g`<div class="row-label">${h}</div>`}
        <div class="control-group">
          ${i?this._motorDirection(t,"down",e,o,r):p}
          ${this._motorDirection(t,"up",e,o,r)}
          ${i?p:g`<button
            class="cg-btn"
            aria-label=${m(this.hass,"action.stop")}
            @click=${()=>this._motorStop(t,e,o)}
            ?disabled=${!c}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?p:this._motorDirection(t,"down",e,o,r)}
        </div>
      </div>
    `}_motorDirection(t,e,i,o,r){let a=t.cover??t[e],c=!!t.cover||!!i;return g`
      <button class="cg-btn"
        aria-label=${m(this.hass,`action.${e}`)}
        @pointerdown=${h=>this._startHold(h,t,e,i,o,r)}
        @pointerup=${h=>this._endPointerHold(h,t,i)}
        @pointercancel=${h=>this._endPointerHold(h,t,i)}
        @keydown=${h=>this._startHold(h,t,e,i,o,r)}
        @keyup=${h=>this._endKeyHold(h,t,i)}
        @click=${h=>this._activateWithoutPointer(h,t,e,i,o)}
        ?disabled=${!a||this._config?.layout==="compact"&&(!c||!this._available(a))}
      ><ha-icon icon=${`mdi:chevron-${e}`}></ha-icon></button>`}_presets(t){return t.presets.length===0?p:g`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${t.presets.map(e=>this._tile(e,()=>this._press(e)))}
      </div>
    `}_utility(t){return t.utility.length===0&&!t.utilitySelects?.length?p:g`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${t.utility.map(e=>this._tile(e,()=>e.startsWith("switch.")?this._call("switch","toggle",e):this._press(e)))}
      </div>
      ${t.utilitySelects?.map(e=>this._moreInfoRow(e))}
    `}_memory(t){let e=t.memory,i=this._config?.memory_slots;if(i&&i.length){let c=new Set(i.map(Number));e=e.filter(h=>c.has(h.slot))}if(e.length===0)return p;let o=this._config?.memory_save!==!1&&e.some(c=>c.save),r=e.map(c=>c.save??c.goto??String(c.slot)).join("|"),a=this._saveModeFor===r;return g`
      <div class="section-heading heading-row">
        <span>${m(this.hass,"section.memory")}</span>
        ${o?g`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${m(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:p}
      </div>
      ${a?g`<div class="hint">${m(this.hass,"memory.set_hint")}</div>`:p}
      <div class="tiles">${e.map(c=>this._memoryTile(c,a))}</div>
    `}_memoryTile(t,e){let i=t.goto??t.save;if(e){let r=!!t.save;return g`
        <button
          class="tile ${r?"save-mode":"is-disabled"}"
          ?disabled=${!r}
          @click=${()=>r&&this._saveMemory(t)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(i)}</span>
        </button>
      `}let o=!!t.goto;return g`
      <button
        class="tile ${o?"":"is-disabled"}"
        ?disabled=${!o}
        @click=${()=>t.goto&&this._press(t.goto)}
      >
        ${this._icon(i)}
        <span class="tile-label">${this._name(i)}</span>
      </button>
    `}_lighting(t){let e=t.lights,i=e.light??e.switch;if(!U(e)&&!e.state)return p;let o=i||e.state||e.level||e.timer||e.toggle||e.cycle||e.timerMinutes||e.timerToggle||e.buttons?.length;return g`
      ${this._heading("section.lighting")}
      ${e.mood&&o?this._subheading("lighting.floor"):p}
      ${i?this._toggleRow(i):p}
      ${e.state?this._moreInfoRow(e.state):p}
      ${e.level?this._moreInfoRow(e.level):p}
      ${e.timer?this._moreInfoRow(e.timer):p}
      ${e.timerMinutes?this._moreInfoRow(e.timerMinutes):p}
      ${!e.timerAppliesImmediately&&(e.timerMinutes||e.timerToggle)?g`<div class="hint">${m(this.hass,"lighting.timer_pending")}</div>`:p}
      ${e.toggle||e.cycle||e.timerToggle||e.buttons?.length?g`<div class="tiles">
              ${e.toggle?this._tile(e.toggle,()=>this._press(e.toggle)):p}
              ${e.cycle?this._tile(e.cycle,()=>this._press(e.cycle)):p}
              ${e.timerToggle?this._tile(e.timerToggle,()=>this._press(e.timerToggle)):p}
              ${e.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
            </div>`:p}
      ${e.mood?g`
        ${this._subheading("lighting.mood")}
        ${e.mood.selects.map(r=>this._moreInfoRow(r))}
        ${e.mood.numbers.map(r=>this._moreInfoRow(r))}
        ${e.mood.toggle||e.mood.buttons?.length?g`<div class="tiles">
          ${e.mood.toggle?this._tile(e.mood.toggle,()=>this._press(e.mood.toggle)):p}
          ${e.mood.buttons?.map(r=>this._tile(r,()=>this._press(r)))}
        </div>`:p}
      `:p}
    `}_massage(t){let e=t.massage;return e.buttons.length===0&&e.numbers.length===0&&!e.selects?.length&&!e.states?.length&&!e.timer?p:g`
      ${this._heading("section.massage")}
      ${e.buttons.length?g`<div class="tiles">
              ${e.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:p}
      ${e.numbers.map(i=>this._moreInfoRow(i))}
      ${e.selects?.map(i=>this._moreInfoRow(i))}
      ${e.states?.map(i=>this._moreInfoRow(i))}
      ${e.timer?this._moreInfoRow(e.timer):p}
    `}_climate(t){let e=[...t.climate.entities,...t.climate.selects,...t.climate.numbers];return e.length===0?p:g`
      ${this._heading("section.climate")}
      ${e.map(i=>this._moreInfoRow(i))}
    `}_connection(t){return!t.connect&&!t.disconnect?p:g`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${t.connect?this._tile(t.connect,()=>this._press(t.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):p}
        ${t.disconnect?this._tile(t.disconnect,()=>this._press(t.disconnect),{icon:"mdi:bluetooth-off"}):p}
      </div>
    `}_heading(t){return g`<div class="section-heading">${m(this.hass,t)}</div>`}_subheading(t){return g`<div class="lighting-heading">${m(this.hass,t)}</div>`}_tile(t,e,i={}){return g`
      <button class="tile ${i.cls??""}" @click=${e}>
        ${this._icon(t,i.icon)}
        <span class="tile-label">${this._name(t)}</span>
      </button>
    `}_onRowKey(t,e){t.target===t.currentTarget&&(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),e())}_toggleRow(t){let i=this._state(t)?.state==="on",o=this._name(t);return g`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${o}
        @click=${()=>this._moreInfo(t)}
        @keydown=${r=>this._onRowKey(r,()=>this._moreInfo(t))}
      >
        ${this._icon(t)}
        <div class="entity-row-text">
          <span>${o}</span>
          <span class="secondary">${this._stateText(t)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${o}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(t)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(t){let e=this._name(t);return g`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${e}
        @click=${()=>this._moreInfo(t)}
        @keydown=${i=>this._onRowKey(i,()=>this._moreInfo(t))}
      >
        ${this._icon(t)}
        <div class="entity-row-text">
          <span>${e}</span>
        </div>
        <span class="secondary value">${this._stateText(t)}</span>
      </div>
    `}_icon(t,e){let i=this._state(t);return i?g`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:g`<ha-icon class="icon" icon=${e??"mdi:bed"}></ha-icon>`}_notice(t){return g`<ha-card><div class="notice">${m(this.hass,t)}</div></ha-card>`}_state(t){return this.hass?.states[t]}_title(t){return this._config?.name?this._config.name:this._deviceName(t)??m(this.hass,"card.default_name")}_deviceName(t=this._config?.device_id){let e=t?this.hass?.devices[t]:void 0;return e?.name_by_user||e?.name||void 0}_name(t){let e=this._state(t)?.attributes.friendly_name??this.hass?.entities[t]?.name??t,i=this.hass?.entities[t]?.device_id,o=this._deviceName(i);return o&&e.startsWith(o+" ")?e.slice(o.length+1):e}_motorName(t){let e=`motor.${t.key}`,i=m(this.hass,e);return i!==e?i:t.key.split("_").map(o=>o.charAt(0).toUpperCase()+o.slice(1)).join(" ")}_angle(t){let e=t.angle??t.position;if(!e)return;let i=Number.parseFloat(this._state(e)?.state??"");return Number.isFinite(i)?i:void 0}_readout(t){let e=t.angle??t.position;if(e){let i=this._angle(t);if(i===void 0)return;let o=this._state(e)?.attributes.unit_of_measurement,r=t.angle?"\xB0":"%";return`${Math.round(i)}${typeof o=="string"?o:r}`}if(t.cover){let i=this._state(t.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(t){let e=this._state(t);if(!e)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(e):e.state}_collectWatched(t){let e=new Set;for(let i of t.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(o=>o&&e.add(o));t.presets.forEach(i=>e.add(i));for(let i of t.memory)[i.goto,i.save].forEach(o=>o&&e.add(o));return[t.stop,t.synchro,t.controlSide,t.connect,t.disconnect,t.connectivity,t.lights.light,t.lights.switch,t.lights.state,t.lights.level,t.lights.toggle,t.lights.cycle,t.lights.timer,t.lights.timerMinutes,t.lights.timerToggle,t.lights.mood?.toggle,t.massage.timer].forEach(i=>i&&e.add(i)),t.firmness.forEach(i=>e.add(i)),t.massage.buttons.forEach(i=>e.add(i)),t.lights.buttons?.forEach(i=>e.add(i)),t.massage.numbers.forEach(i=>e.add(i)),t.massage.selects?.forEach(i=>e.add(i)),t.massage.states?.forEach(i=>e.add(i)),t.lights.mood?.selects.forEach(i=>e.add(i)),t.lights.mood?.numbers.forEach(i=>e.add(i)),t.lights.mood?.buttons?.forEach(i=>e.add(i)),t.utility.forEach(i=>e.add(i)),t.utilitySelects?.forEach(i=>e.add(i)),t.climate.entities.forEach(i=>e.add(i)),t.climate.selects.forEach(i=>e.add(i)),t.climate.numbers.forEach(i=>e.add(i)),[...e]}_startHold(t,e,i,o,r,a){let c=null;if(t instanceof KeyboardEvent){if(t.repeat||t.key!=="Enter"&&t.key!==" ")return;t.preventDefault()}else{if(t.button!==0||!t.isPrimary)return;t.currentTarget.setPointerCapture?.(t.pointerId),t.preventDefault(),c=t.pointerId}this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate()),this._hold.start(e,i,c,o,r??(o?[o]:[]),a,t instanceof KeyboardEvent?t.key:null)}_activateWithoutPointer(t,e,i,o,r){t.detail!==0||this._hold.heldKey!==null||(this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):e.cover&&this._compactStopTargets.set(e.cover,Symbol()),this.requestUpdate()),this._hold.claimStopScope([...r??[],...o?[o]:[],...e.cover?[e.cover]:[]]),de(this.hass,e,i))}_endPointerHold(t,e,i){this._hold.endFromPointer(e,t.pointerId,t.type!=="pointerup"||t.button===0,i)}_endKeyHold(t,e,i){t.key!=="Enter"&&t.key!==" "||(t.stopPropagation(),this._hold.endKeyboard(e,i,t.key))}_motorStop(t,e,i){if(t.cover){_t(this._hold,t.cover,[...i??(e?[e]:[]),t.cover],t.coverStopScope==="side"?void 0:t.key);return}_t(this._hold,e,i)}_toggleSaveMode(t){this._saveModeFor=this._saveModeFor===t?void 0:t}_saveMemory(t){t.save&&this._press(t.save),this._saveModeFor=void 0}_call(t,e,i){this.hass?.callService(t,e,{entity_id:i})?.catch(()=>{})}_press(t){this._call("button","press",t)}_toggle(t){this._call("homeassistant","toggle",t)}_setEntities(t,e){this.hass?.callService("homeassistant",e?"turn_on":"turn_off",{entity_id:t})?.catch(()=>{})}_moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:t},bubbles:!0,composed:!0}))}};S.styles=J`
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
  `,w([W({attribute:!1})],S.prototype,"hass",2),w([M()],S.prototype,"_config",2),w([M()],S.prototype,"_saveModeFor",2),w([M()],S.prototype,"_activePairedPane",2),w([M()],S.prototype,"_synchronizingTo",2),w([M()],S.prototype,"_synchronizationFailed",2);at("adjustable-bed-card",S);console.info(`%c adjustable-bed-card %c ${_e} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{S as AdjustableBedCard};
