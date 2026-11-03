/* adjustable-bed-card 4.2.4 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var Tt=Object.defineProperty;var Ct=Object.getOwnPropertyDescriptor;var T=(n,s,e,t)=>{for(var i=t>1?void 0:t?Ct(s,e):s,o=n.length-1,r;o>=0;o--)(r=n[o])&&(i=(t?r(s,e,i):r(i))||i);return t&&i&&Tt(s,e,i),i};var L="adjustable_bed";function X(n){for(let s of["left","right","both"]){let e=`_${s}`;if(n.endsWith(e))return{key:n.slice(0,-e.length),side:s}}return{key:n}}var W=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],Je=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],Ce=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_swing","preset_incline","preset_both_up","preset_yoga"],At={back:"back",foot:"feet",pillow:"pillow"},Mt=new Set(["elevate_both","starcode_m1x12_part_1","starcode_m1x12_part_2","starcode_m1x12_part_4","starcode_m1x12_part_8","starcode_m1x12_part_16"]),Rt=n=>n.split(".",1)[0],Ae=n=>n.translation_key??"";function Pt(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[],numbers:[]},utility:[],utilityStates:[]}}function S(n,s,e){let t=Pt();if(!s||!n?.entities)return t;let i=()=>t.lights.mood??={selects:[],numbers:[]},o=n.devices?.[s]?.parent_device_id||Object.values(n.devices??{}).some(f=>f.parent_device_id===s),r=Object.values(n.entities).filter(f=>f.device_id===s&&f.platform===L),l=!!e||!!o&&!r.some(f=>f.translation_key==="ble_connection"),c=new Map,h=f=>{let d=c.get(f);return d||(d=Mt.has(f)?{key:f,coverStopScope:"side"}:{key:f},c.set(f,d)),d},_=(f,d,de,G)=>{let w=h(d);w[de]=f;let z=n.states[f]?.attributes,U=z?.held_control,a=z?.hold_start_delay_ms,k=z?.hold_release_delay_ms;typeof U=="string"&&typeof a=="number"&&typeof k=="number"&&G&&z?.paired_hold_motor===void 0&&(w.deviceId=G,w.holdEntityId=f,w.heldControls={...w.heldControls,[de]:{control:U,startDelayMs:a,releaseDelayMs:k}});let E=z?.paired_hold_motor;E==="back"||E==="legs"||E==="lumbar"?w.timedMove={deviceId:s,motor:E,...z?.paired_hold_side==="both"?{side:"both"}:{}}:(d==="back"||d==="legs"||d==="lumbar")&&typeof U=="string"&&(w.timedMove={deviceId:s,motor:d})},m=new Map,b=new Map,x=f=>{let d=b.get(f);return d||(d={slot:f},b.set(f,d)),d};for(let f of r){if(f.hidden)continue;let d=f.entity_id,de=Rt(d),G=Ae(f);if(!G)continue;let w=X(G),U=n.states[d]?.attributes.bed_side??n.states[d]?.attributes.side??w.side;if(e&&U!==e)continue;let a=l&&w.side===U?w.key:G,k;switch(de){case"cover":{let E=h(a);E.cover=d;let M=n.states[d]?.attributes,Ve=M?.held_control_up,Ye=M?.held_control_down;if((M?.held_stop_scope==="motor"||M?.held_stop_scope==="side")&&(E.coverStopScope=M.held_stop_scope),typeof Ve=="string"&&typeof Ye=="string"){(a==="back"||a==="legs"||a==="lumbar")&&(E.timedMove={deviceId:s,motor:a});let Q=M?.hold_start_delay_ms,Z=M?.hold_release_delay_ms;(M?.held_stop_scope==="motor"||M?.held_stop_scope==="side")&&f.device_id&&typeof Q=="number"&&Number.isFinite(Q)&&Q>=0&&typeof Z=="number"&&Number.isFinite(Z)&&Z>=0&&(E.deviceId=f.device_id,E.holdEntityId=d,E.heldControls={up:{control:Ve,startDelayMs:Q,releaseDelayMs:Z},down:{control:Ye,startDelayMs:Q,releaseDelayMs:Z}})}}break;case"sensor":a.endsWith("_angle")?h(a.slice(0,-6)).angle=d:a.startsWith("sleepys_app_position_")||a.startsWith("sleepys_app_field_")?t.utilityStates?.push(d):a.startsWith("reverie_")&&a.endsWith("_massage_intensity")?(t.massage.states??=[]).push(d):a==="sleepys_app_massage_timer_code"||a==="reverie_pairlink_massage_mode"||a==="reverie_pairlink_massage_timer"?(t.massage.states??=[]).push(d):a==="reverie_massage_wave"?(t.massage.states??=[]).push(d):a==="logicdata_air_pump_pressure"?t.firmness.push(d):a==="innova_massage_timer"||a==="glideaway_motion_massage_timer"||a==="bedsense_massage_timer"?t.massage.timer=d:a==="bedsense_light_duration"?t.lights.state=d:/^bedsense_(head_bar|wave_bar|head_steps|foot_steps|wave_steps)$/.test(a)&&(t.massage.states??=[]).push(d);break;case"number":a.endsWith("_position")?h(a.slice(0,-9)).position=d:a==="reverie_body_tilt"?h("lumbar").position=d:!e&&w.side&&w.key.endsWith("_position")?h(`${w.key.slice(0,-9)}_${w.side}`).position=d:a.startsWith("massage_")&&a.endsWith("_intensity")||a==="reverie_wave_level"||a==="reverie_massage_wave"||a==="reverie_stk_head_wave"||a==="reverie_stk_global_massage"?t.massage.numbers.push(d):a==="reverie_pairlink_massage_timer"?t.massage.timer=d:a==="light_level"||a==="svane_intensity"||a==="starcode_brightness"||a==="vmatbasic_floor_level"||a==="starcode_abm5_4_light_level"?t.lights.level=d:a==="vmatbasic_floor_minutes"?(t.lights.timerMinutes=d,t.lights.timerAppliesImmediately=!0):a==="vibradorm_app_floor_timer_minutes"?t.lights.timerMinutes=d:(k=a.match(/^richmat_mh_(back|foot|pillow)_angle$/))?h(At[k[1]]).position=d:a==="richmat_mh_light_timer"?t.lights.timer=d:a==="richmat_mh_light_timer_minutes"?(t.lights.timerMinutes=d,t.lights.timerAppliesImmediately=!0):a==="richmat_mh_head_massage_intensity"||a==="richmat_mh_foot_massage_intensity"?t.massage.numbers.push(d):a==="vibradorm_app_mood_speed"||a==="vmatbasic_mood_speed"||a==="vmatbasic_mood_brightness"?i().numbers.push(d):a==="vibradorm_app_massage_speed"||a==="sleeptracker_wave_minutes"?t.massage.numbers.push(d):a==="sleepys_app_color_code"?(t.lights.numbers??=[]).push(d):a.startsWith("sleepys_app_target_axis_")?(t.utilityNumbers??=[]).push(d):/^sleeptracker_(left|right)_level$/.test(a)||a==="fan_level"?t.climate.numbers.push(d):a.startsWith("sleep_number_setting")&&t.firmness.push(d);break;case"button":Ce.includes(a)||a.startsWith("preset_")||a.startsWith("sleepys_app_preset_")?(k=a.match(/^preset_memory_(\d+)$/))?x(Number(k[1])).goto=d:m.set(a,d):(k=a.match(/^program_memory_(\d+)$/))?x(Number(k[1])).save=d:(k=a.match(/^sleepys_app_memory_(\d+)$/))?x(Number(k[1])).goto=d:a==="stop"||a==="stop_both"?t.stop=d:a==="connect"?t.connect=d:a==="disconnect"?t.disconnect=d:a==="bedsense_light"?(t.lights.buttons??=[]).push(d):a==="bedsense_massage"?t.massage.buttons.push(d):a==="bedsense_action"?t.utility.push(d):a==="sleeptracker_light_toggle"?t.lights.toggle=d:a==="sleeptracker_light_off"?(t.lights.buttons??=[]).push(d):/^sleeptracker_(massage_|wave_start|wind_down_|local_animation)/.test(a)?t.massage.buttons.push(d):a.startsWith("sleeptracker_")?t.utility.push(d):a.startsWith("sleepys_app_light_")||a.startsWith("sleepys_app_voice_brightness_")||a==="sleepys_app_rgb_action"?(t.lights.buttons??=[]).push(d):a.startsWith("sleepys_app_massage_")?t.massage.buttons.push(d):a==="toggle_light"?t.lights.toggle=d:a==="light_cycle"||a==="starcode_light_cycle"?t.lights.cycle=d:a==="vibradorm_app_mood_toggle"||a==="vmatbasic_mood_toggle"?i().toggle=d:a==="vmatbasic_mood_nightlight"?(i().buttons??=[]).push(d):a==="vmatbasic_floor_toggle"||a==="vmatbasic_floor_hold"?t.lights.toggle=d:a.startsWith("vmatbasic_massage_")?t.massage.buttons.push(d):a==="vibradorm_app_floor_timer_toggle"?t.lights.timerToggle=d:a==="remacro_led_brightness_save"?(t.lights.buttons??=[]).push(d):a==="starcode_abm5_4_light_plus"||a==="starcode_abm5_4_light_minus"||a==="starcode_abm5_4_light_on"||a==="starcode_abm5_4_light_off"?(t.lights.buttons??=[]).push(d):a==="starcode_abm5_4_massage_release"?t.massage.buttons.push(d):a.startsWith("starcode_abm5_4_")?t.utility.push(d):a==="okin_app_home"||a.startsWith("simmons_inclined")?m.set(a,d):a==="simmons_sync_clock"||a==="simmons_refresh_alarms"||a==="glideaway_motion_query_alarm"?t.utility.push(d):a.startsWith("eshine_massage_")?t.massage.buttons.push(d):a.startsWith("eshine_save_")?t.utility.push(d):a==="richmat_mh_massage"?t.massage.buttons.push(d):a==="richmat_mh_preset"?m.set(`${a}:${d}`,d):a.startsWith("richmat_mh_")?t.utility.push(d):a.startsWith("adjustable_lumbar_wave_")||a==="adjustable_lumbar_massage_on"?t.massage.buttons.push(d):a.startsWith("adjustable_lumbar_")?t.utility.push(d):a==="logicdata_app_query_massage"?t.massage.buttons.push(d):a.startsWith("logicdata_air_pump_")?t.utility.push(d):/^comfort_enhancements_(head|foot|timer)_cycle$/.test(a)||a==="ore_comfort_massage_start"||a==="innova_massage_level"||a==="innova_massage_timer_hold"?t.massage.buttons.push(d):a==="ore_comfort_program_flat"||a==="ore_comfort_program_zero_g"?t.utility.push(d):a==="coolbase_head_massage"||a==="coolbase_foot_massage"||a==="coolbase_massage_mode"?t.massage.buttons.push(d):a==="comfort_enhancements_quiet_sleep"?m.set(a,d):a==="restonic_zzz"||a.startsWith("coolbase_")?t.utility.push(d):a==="vibradorm_app_massage_automatic"||a==="vibradorm_app_massage_individual"?t.massage.buttons.push(d):a==="sync_positions"||a==="child_lock_toggle"||a==="auxiliary_action"||a==="remote_action"||a==="solace_music_toggle"||a==="solace_music_off"||a==="wake_controller"||a==="reset_defaults"||a==="factory_reset"||a==="vibradorm_app_all_up"||a==="vibradorm_app_all_down"||a==="vibradorm_app_sync"||a==="vibradorm_app_refresh_info"||a==="vmatbasic_all_up"||a==="vmatbasic_all_down"||a==="vmatbasic_refresh_info"||a.startsWith("starcode_save_")||a==="starcode_reset"||a==="starcode_query"||a==="starcode_light_mode"?t.utility.push(d):a.startsWith("massage_")?t.massage.buttons.push(d):a.startsWith("sleepys_app_")?t.utility.push(d):(k=a.match(/^(.+)_(up|down)$/))&&_(d,k[1],k[2],f.device_id);break;case"switch":a==="under_bed_lights"?t.lights.switch=d:a==="synchro_mode"?t.synchro=d:(a==="linak_automatic_drive"||a==="automatic_light")&&t.utility.push(d);break;case"light":t.lights.light=d;break;case"binary_sensor":a==="ble_connection"?t.connectivity=d:a==="sleeptracker_wind_down_running"?(t.massage.states??=[]).push(d):a==="reverie_pairlink_low_battery"?t.utility.push(d):a==="under_bed_lights"||a==="adjustable_lite_light"||a==="innova_light"||a==="sleeptracker_light_on"?t.lights.state=d:a.startsWith("bed_presence")&&t.presence.push(d);break;case"select":a==="motion_bed_active_module"||a.startsWith("okin_app_")?(t.utilitySelects??=[]).push(d):a==="reverie_stk_side"?(t.utilitySelects??=[]).push(d):a==="reverie_pairlink_massage_mode"||a==="reverie_pairlink_massage_rhythm"?(t.massage.selects??=[]).push(d):a==="light_timer"?t.lights.timer=d:a==="remacro_control_side"?t.controlSide=d:a==="starcode_color"||a==="vibradorm_app_mood_palette"||a==="vibradorm_app_mood_effect"||a==="vmatbasic_mood_palette"||a==="vmatbasic_mood_effect"?i().selects.push(d):a==="sleeptracker_wave_frequency"||/^sleeptracker_massage_(head_level|foot_level|pattern_option)$/.test(a)?(t.massage.selects??=[]).push(d):/^sleeptracker_(left|right)_(mode|curve)$/.test(a)?t.climate.selects.push(d):a==="vibradorm_app_massage_wave"?(t.massage.selects??=[]).push(d):a==="richmat_mh_motor_mode"||a==="richmat_mh_snore"?(t.utilitySelects??=[]).push(d):a.startsWith("richmat_mh_waist_")?(t.massage.selects??=[]).push(d):a==="massage_timer"||a==="starcode_abm5_4_massage_timer"||a==="ore_comfort_massage_timer"?t.massage.timer=d:/thermal|footwarming|foundation/.test(a)&&t.climate.selects.push(d);break;case"climate":t.climate.entities.push(d);break}}let $=[...c.keys()],y=[...Je.filter(f=>c.has(f)),...$.filter(f=>!Je.includes(f)).sort()];t.motors=y.map(f=>c.get(f)).filter(f=>f.cover||f.up||f.down||f.angle||f.position);let v=[...m.keys()];return t.presets=[...Ce.filter(f=>m.has(f)),...v.filter(f=>!Ce.includes(f)).sort()].map(f=>m.get(f)),t.memory=[...b.values()].filter(f=>f.goto||f.save).sort((f,d)=>f.slot-d.slot),t}function he(n,s){return!s||!n?.entities?!1:Object.values(n.entities).some(e=>e.device_id===s&&e.platform===L&&(n.states[e.entity_id]?.attributes.bed_side==="both"||X(Ae(e)).side==="both"))}function ee(n,s){if(!s||!n?.devices)return[];let e=i=>{let o=n.devices[i];return(o?.name_by_user??o?.name??i).toLowerCase()},t=i=>{for(let o of Object.values(n.entities??{})){if(o.device_id!==i||o.platform!=="adjustable_bed")continue;let r=n.states[o.entity_id]?.attributes.bed_side??X(Ae(o)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(n.devices).filter(i=>(i.parent_device_id??i.via_device_id)===s).map(i=>i.id).sort((i,o)=>t(i)-t(o)||e(i).localeCompare(e(o)))}function pe(n,s){if(!s||!n?.devices)return s;let e=n.devices[s]?.parent_device_id??n.devices[s]?.via_device_id;return e&&n.devices[e]&&ee(n,e).length?e:s}function P(n){let s=n.lights;return n.motors.length===0&&!n.synchro&&!n.controlSide&&n.firmness.length===0&&n.presets.length===0&&n.memory.length===0&&!n.stop&&!n.connect&&!n.disconnect&&!n.connectivity&&!I(s)&&!s.state&&n.massage.buttons.length===0&&n.massage.numbers.length===0&&!n.massage.selects?.length&&!n.massage.states?.length&&!n.massage.timer&&n.climate.entities.length===0&&n.climate.selects.length===0&&n.climate.numbers.length===0&&n.utility.length===0&&!n.utilityNumbers?.length&&!n.utilitySelects?.length&&!n.utilityStates?.length}function I(n){return!!(n.light||n.switch||n.level||n.toggle||n.numbers?.length||n.buttons?.length||n.cycle||n.timer||n.timerMinutes||n.timerToggle||n.mood?.toggle||n.mood?.selects.length||n.mood?.numbers.length||n.mood?.buttons?.length)}var Me="adjustable-bed-card",Qe={type:Me,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(n,s)=>{let e=n.entities[s];return e?.platform!==L||!e.device_id?null:{config:{type:`custom:${Me}`,device_id:e.device_id}}}};function Ht(n){let s=n.customCards??=[],e=s.findIndex(t=>t.type===Me);e===-1?s.push(Qe):s[e]=Qe}function ue(n,s,e=window){let t=e.customElements;t.get(n)||t.define(n,s),t.whenDefined("home-assistant").then(()=>{let i=e.customElements;i!==t&&!i.get(n)&&i.define(n,s)})}typeof window<"u"&&Ht(window);var ge=globalThis,me=ge.ShadowRoot&&(ge.ShadyCSS===void 0||ge.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Re=Symbol(),Ze=new WeakMap,te=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==Re)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(me&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=Ze.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&Ze.set(e,s))}return s}toString(){return this.cssText}},Xe=n=>new te(typeof n=="string"?n:n+"",void 0,Re),ie=(n,...s)=>{let e=n.length===1?n[0]:s.reduce((t,i,o)=>t+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[o+1],n[0]);return new te(e,n,Re)},et=(n,s)=>{if(me)n.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=ge.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,n.appendChild(t)}},Pe=me?n=>n:n=>n instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return Xe(e)})(n):n;var{is:Bt,defineProperty:zt,getOwnPropertyDescriptor:Lt,getOwnPropertyNames:Ot,getOwnPropertySymbols:jt,getPrototypeOf:Dt}=Object,_e=globalThis,tt=_e.trustedTypes,Nt=tt?tt.emptyScript:"",Ft=_e.reactiveElementPolyfillSupport,se=(n,s)=>n,oe={toAttribute(n,s){switch(s){case Boolean:n=n?Nt:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,s){let e=n;switch(s){case Boolean:e=n!==null;break;case Number:e=n===null?null:Number(n);break;case Object:case Array:try{e=JSON.parse(n)}catch{e=null}}return e}},fe=(n,s)=>!Bt(n,s),it={attribute:!0,type:String,converter:oe,reflect:!1,useDefault:!1,hasChanged:fe};Symbol.metadata??=Symbol("metadata"),_e.litPropertyMetadata??=new WeakMap;var R=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=it){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&zt(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:o}=Lt(this.prototype,s)??{get(){return this[e]},set(r){this[e]=r}};return{get:i,set(r){let l=i?.call(this);o?.call(this,r),this.requestUpdate(s,l,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??it}static _$Ei(){if(this.hasOwnProperty(se("elementProperties")))return;let s=Dt(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(se("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(se("properties"))){let e=this.properties,t=[...Ot(e),...jt(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(Pe(i))}else s!==void 0&&e.push(Pe(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return et(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let o=(t.converter?.toAttribute!==void 0?t.converter:oe).toAttribute(e,t.type);this._$Em=s,o==null?this.removeAttribute(i):this.setAttribute(i,o),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let o=t.getPropertyOptions(i),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:oe;this._$Em=i;let l=r.fromAttribute(e,o.type);this[i]=l??this._$Ej?.get(i)??l,this._$Em=null}}requestUpdate(s,e,t,i=!1,o){if(s!==void 0){let r=this.constructor;if(i===!1&&(o=this[s]),t??=r.getPropertyOptions(s),!((t.hasChanged??fe)(o,e)||t.useDefault&&t.reflect&&o===this._$Ej?.get(s)&&!this.hasAttribute(r._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:o},r){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,r??e??this[s]),o!==!0||r!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,o]of this._$Ep)this[i]=o;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,o]of t){let{wrapped:r}=o,l=this[i];r!==!0||this._$AL.has(i)||l===void 0||this.C(i,void 0,o,l)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};R.elementStyles=[],R.shadowRootOptions={mode:"open"},R[se("elementProperties")]=new Map,R[se("finalized")]=new Map,Ft?.({ReactiveElement:R}),(_e.reactiveElementVersions??=[]).push("2.1.2");var De=globalThis,st=n=>n,ve=De.trustedTypes,ot=ve?ve.createPolicy("lit-html",{createHTML:n=>n}):void 0,dt="$lit$",H=`lit$${Math.random().toFixed(9).slice(2)}$`,ht="?"+H,Kt=`<${ht}>`,D=document,re=()=>D.createComment(""),ae=n=>n===null||typeof n!="object"&&typeof n!="function",Ne=Array.isArray,Gt=n=>Ne(n)||typeof n?.[Symbol.iterator]=="function",He=`[ \t
\f\r]`,ne=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,nt=/-->/g,rt=/>/g,O=RegExp(`>|${He}(?:([^\\s"'>=/]+)(${He}*=${He}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),at=/'/g,lt=/"/g,pt=/^(?:script|style|textarea|title)$/i,Fe=n=>(s,...e)=>({_$litType$:n,strings:s,values:e}),u=Fe(1),be=Fe(2),di=Fe(3),N=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),ct=new WeakMap,j=D.createTreeWalker(D,129);function ut(n,s){if(!Ne(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return ot!==void 0?ot.createHTML(s):s}var Ut=(n,s)=>{let e=n.length-1,t=[],i,o=s===2?"<svg>":s===3?"<math>":"",r=ne;for(let l=0;l<e;l++){let c=n[l],h,_,m=-1,b=0;for(;b<c.length&&(r.lastIndex=b,_=r.exec(c),_!==null);)b=r.lastIndex,r===ne?_[1]==="!--"?r=nt:_[1]!==void 0?r=rt:_[2]!==void 0?(pt.test(_[2])&&(i=RegExp("</"+_[2],"g")),r=O):_[3]!==void 0&&(r=O):r===O?_[0]===">"?(r=i??ne,m=-1):_[1]===void 0?m=-2:(m=r.lastIndex-_[2].length,h=_[1],r=_[3]===void 0?O:_[3]==='"'?lt:at):r===lt||r===at?r=O:r===nt||r===rt?r=ne:(r=O,i=void 0);let x=r===O&&n[l+1].startsWith("/>")?" ":"";o+=r===ne?c+Kt:m>=0?(t.push(h),c.slice(0,m)+dt+c.slice(m)+H+x):c+H+(m===-2?l:x)}return[ut(n,o+(n[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},le=class n{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let o=0,r=0,l=s.length-1,c=this.parts,[h,_]=Ut(s,e);if(this.el=n.createElement(h,t),j.currentNode=this.el.content,e===2||e===3){let m=this.el.content.firstChild;m.replaceWith(...m.childNodes)}for(;(i=j.nextNode())!==null&&c.length<l;){if(i.nodeType===1){if(i.hasAttributes())for(let m of i.getAttributeNames())if(m.endsWith(dt)){let b=_[r++],x=i.getAttribute(m).split(H),$=/([.?@])?(.*)/.exec(b);c.push({type:1,index:o,name:$[2],strings:x,ctor:$[1]==="."?ze:$[1]==="?"?Le:$[1]==="@"?Oe:V}),i.removeAttribute(m)}else m.startsWith(H)&&(c.push({type:6,index:o}),i.removeAttribute(m));if(pt.test(i.tagName)){let m=i.textContent.split(H),b=m.length-1;if(b>0){i.textContent=ve?ve.emptyScript:"";for(let x=0;x<b;x++)i.append(m[x],re()),j.nextNode(),c.push({type:2,index:++o});i.append(m[b],re())}}}else if(i.nodeType===8)if(i.data===ht)c.push({type:2,index:o});else{let m=-1;for(;(m=i.data.indexOf(H,m+1))!==-1;)c.push({type:7,index:o}),m+=H.length-1}o++}}static createElement(s,e){let t=D.createElement("template");return t.innerHTML=s,t}};function q(n,s,e=n,t){if(s===N)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,o=ae(s)?void 0:s._$litDirective$;return i?.constructor!==o&&(i?._$AO?.(!1),o===void 0?i=void 0:(i=new o(n),i._$AT(n,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=q(n,i._$AS(n,s.values),i,t)),s}var Be=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??D).importNode(e,!0);j.currentNode=i;let o=j.nextNode(),r=0,l=0,c=t[0];for(;c!==void 0;){if(r===c.index){let h;c.type===2?h=new ce(o,o.nextSibling,this,s):c.type===1?h=new c.ctor(o,c.name,c.strings,this,s):c.type===6&&(h=new je(o,this,s)),this._$AV.push(h),c=t[++l]}r!==c?.index&&(o=j.nextNode(),r++)}return j.currentNode=D,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},ce=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=q(this,s,e),ae(s)?s===p||s==null||s===""?(this._$AH!==p&&this._$AR(),this._$AH=p):s!==this._$AH&&s!==N&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):Gt(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==p&&ae(this._$AH)?this._$AA.nextSibling.data=s:this.T(D.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=le.createElement(ut(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let o=new Be(i,this),r=o.u(this.options);o.p(e),this.T(r),this._$AH=o}}_$AC(s){let e=ct.get(s.strings);return e===void 0&&ct.set(s.strings,e=new le(s)),e}k(s){Ne(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let o of s)i===e.length?e.push(t=new n(this.O(re()),this.O(re()),this,this.options)):t=e[i],t._$AI(o),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=st(s).nextSibling;st(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},V=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,o){this.type=1,this._$AH=p,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=o,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=p}_$AI(s,e=this,t,i){let o=this.strings,r=!1;if(o===void 0)s=q(this,s,e,0),r=!ae(s)||s!==this._$AH&&s!==N,r&&(this._$AH=s);else{let l=s,c,h;for(s=o[0],c=0;c<o.length-1;c++)h=q(this,l[t+c],e,c),h===N&&(h=this._$AH[c]),r||=!ae(h)||h!==this._$AH[c],h===p?s=p:s!==p&&(s+=(h??"")+o[c+1]),this._$AH[c]=h}r&&!i&&this.j(s)}j(s){s===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},ze=class extends V{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===p?void 0:s}},Le=class extends V{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==p)}},Oe=class extends V{constructor(s,e,t,i,o){super(s,e,t,i,o),this.type=5}_$AI(s,e=this){if((s=q(this,s,e,0)??p)===N)return;let t=this._$AH,i=s===p&&t!==p||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,o=s!==p&&(t===p||i);i&&this.element.removeEventListener(this.name,this,t),o&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},je=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){q(this,s)}};var Wt=De.litHtmlPolyfillSupport;Wt?.(le,ce),(De.litHtmlVersions??=[]).push("3.3.3");var gt=(n,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let o=e?.renderBefore??null;t._$litPart$=i=new ce(s.insertBefore(re(),o),o,void 0,e??{})}return i._$AI(n),i};var Ke=globalThis,C=class extends R{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=gt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return N}};C._$litElement$=!0,C.finalized=!0,Ke.litElementHydrateSupport?.({LitElement:C});var It=Ke.litElementPolyfillSupport;It?.({LitElement:C});(Ke.litElementVersions??=[]).push("4.2.2");var qt={attribute:!0,type:String,converter:oe,reflect:!1,hasChanged:fe},Vt=(n=qt,s,e)=>{let{kind:t,metadata:i}=e,o=globalThis.litPropertyMetadata.get(i);if(o===void 0&&globalThis.litPropertyMetadata.set(i,o=new Map),t==="setter"&&((n=Object.create(n)).wrapped=!0),o.set(e.name,n),t==="accessor"){let{name:r}=e;return{set(l){let c=s.get.call(this);s.set.call(this,l),this.requestUpdate(r,c,n,!0,l)},init(l){return l!==void 0&&this.C(r,void 0,n,l),l}}}if(t==="setter"){let{name:r}=e;return function(l){let c=this[r];s.call(this,l),this.requestUpdate(r,c,n,!0,l)}}throw Error("Unsupported decorator location: "+t)};function Y(n){return(s,e)=>typeof e=="object"?Vt(n,s,e):((t,i,o)=>{let r=i.hasOwnProperty(o);return i.constructor.createProperty(o,t),r?Object.getOwnPropertyDescriptor(i,o):void 0})(n,s,e)}function B(n){return Y({...n,state:!0,attribute:!1})}var F=n=>Math.max(0,Math.min(75,n));function Ge(n,s="theme"){let e=F(n.upper.angle??0),t=F(n.lower.angle??0),i=`rotate(${e} 150 70)`,o=`rotate(${-t} 150 70)`,r=l=>l.angle===void 0?"":`${l.label?`${l.label} `:""}${Math.round(F(l.angle))}\xB0`;return be`
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
  `}function Ue(n){let s=F(n.left.upper.angle??0),e=F(n.left.lower.angle??0),t=F(n.right.upper.angle??0),i=F(n.right.lower.angle??0),o=(r,l,c,h)=>be`
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
        transform=${`rotate(${l} 150 70)`}
      >
        <rect class="dual-bed-surface" x="42" y="58" width="108" height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
    </g>
  `;return be`
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
  `}function We(n){let s=n.find(t=>t.key==="back"||t.key==="head"),e=n.find(t=>t.key==="legs"||t.key==="feet");return s&&e?{upper:s,lower:e}:void 0}function mt(n,s){let e=n.motors.filter(t=>{let i=t.angle??t.position;return s.states[i??""]?.attributes.unit_of_measurement==="\xB0"});return We(e)!==void 0}function _t(n,s){let e=n?.entities[s]?.device_id,t=n?.states[s]?.attributes,i=t?.held_control,o=t?.hold_start_delay_ms,r=t?.hold_release_delay_ms;if(!(!e||typeof i!="string"||typeof o!="number"||!Number.isFinite(o)||o<0||typeof r!="number"||!Number.isFinite(r)||r<0))return{key:s,up:s,deviceId:e,holdEntityId:s,heldControl:{control:i,startDelayMs:o,releaseDelayMs:r}}}function Ie(n,s,e){if(s.timedMove)return n?.callService("adjustable_bed","timed_move",{device_id:s.timedMove.deviceId,...s.timedMove.side?{side:s.timedMove.side}:{},motor:s.timedMove.motor,direction:e,duration_ms:1e3});if(s.cover)return n?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:s.cover});let t=e==="up"?s.up:s.down;return t?n?.callService("button","press",{entity_id:t}):void 0}function ft(n,s,e){let t=s.heldControls?.[e]??s.heldControl;if(!t||!s.deviceId)return;let i=n?.states[s.holdEntityId??s.cover??""]?.attributes.bed_side,o={device_id:[s.deviceId],control:t.control,duration:60};return(i==="left"||i==="right"||i==="both")&&(o.side=i),n?.callService("adjustable_bed","hold_control",o)}function vt(n,s,e){Ie(n,s,e)?.catch(()=>{})}function bt(n,s,e,t){let i=()=>t(),o=()=>{e()&&t()};n.addEventListener("blur",i),s.addEventListener("visibilitychange",o);let r=!0;return()=>{r&&(r=!1,n.removeEventListener("blur",i),s.removeEventListener("visibilitychange",o))}}function $e(n,s){if(!n||!s)return;let e=n.entities[s]?.device_id;if(!e)return;let t=n.devices??{},i=t[e],o=n.states[s]?.attributes.bed_side??n.states[s]?.attributes.side,r=o==="left"||o==="right"||o==="both"?o:Object.values(t).some(l=>l.parent_device_id===e)?"both":void 0;return{deviceId:i?.parent_device_id??e,side:r}}var xe=class{constructor(s,e={setTimeout:(t,i)=>globalThis.setTimeout(t,i),clearTimeout:t=>globalThis.clearTimeout(t)}){this.actions=s;this.timers=e;this._key=null;this._motor=null;this._scopeStops=[];this._remainingStops=[];this._stopTargetGenerations=new Map;this._keyboardKey=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0;this._repeatBlocked=!1;this._started=!1;this._releaseId=0;this._pendingReleases=new Map}get heldKey(){return this._key}start(s,e,t,i,o=i?[i]:[],r=[],l=null,c){if(this._key!==null)return;let h=Array.isArray(o)?o:[];this._target=Array.isArray(o)?c:o,this._flushPendingForTarget(i??s.cover??s.key),this._key=s.key,this._motor=Object.freeze({...s,...s.timedMove?{timedMove:Object.freeze({...s.timedMove})}:{}}),this._cover=s.cover??null,this._stop=i??null,this._scopeStops=[...new Set([...h,...i?[i]:[],...s.cover?[s.cover]:[],...this._targetScope(this._target)])],this._remainingStops=[...new Set(r)],this.claimStopScope(this._scopeStops),this._pointerId=t,this._keyboardKey=l;let _=++this._generation;if(this._heldControl=s.heldControls?.[e]??s.heldControl,this._heldControl){let m=this._heldControl.startDelayMs;m<=0?this._startHeldControl(this._motor,e,_):this._startTimer=this.timers.setTimeout(()=>this._startHeldControl(this._motor??s,e,_),m);return}this._started=!0,this._repeat(this._motor,e,_)}_targetScope(s){return s?(s.side==="left"||s.side==="right"?[s.side]:["left","right"]).map(t=>`target:${s.deviceId}:${t}`):[]}claimStopScope(s,e){for(let t of new Set([...s,...this._targetScope(e)]))this._stopTargetGenerations.set(t,(this._stopTargetGenerations.get(t)??0)+1)}_startHeldControl(s,e,t){this._startTimer=void 0,!(t!==this._generation||this._key!==s.key)&&(this._started=!0,this._holdControl(s,e,t))}async _holdControl(s,e,t){try{let i=this.actions.holdControl?.(s,e);i&&await i}catch{}finally{t===this._generation&&this._reset()}}async _repeat(s,e,t){let i=this._motor;if(i)for(;t===this._generation&&!this._repeatBlocked;)try{let o=this.actions.pulse(i,e);if(!o)return;this._pulseInFlight=o;try{await o}finally{this._pulseInFlight===o&&(this._pulseInFlight=void 0)}}catch{return}}_targetKey(s=this._stop??void 0,e=this._cover??void 0){return s??e??this._key??""}_release(s){s.cover?this.actions.stopCover(s.cover,s.stopEntityId):this.actions.stopBed(s.stopEntityId)}_scheduleRelease(){let s={id:++this._releaseId,motorKey:this._key??"",targetKey:this._targetKey(),target:this._target,cover:this._cover??void 0,stopEntityId:this._stop??void 0,scopeGenerations:new Map(this._scopeStops.map(t=>[t,this._stopTargetGenerations.get(t)??0]))};this._pendingReleases.set(s.id,s);let e=this._heldControl?.releaseDelayMs??0;if(e<=0){this._runRelease(s);return}s.timer=this.timers.setTimeout(()=>this._runRelease(s),e)}_runRelease(s){this._pendingReleases.delete(s.id)&&(s.timer!==void 0&&this.timers.clearTimeout(s.timer),[...s.scopeGenerations].every(([e,t])=>this._stopTargetGenerations.get(e)===t)&&this._release(s))}_flushPendingForTarget(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s&&(this._runRelease(t),e.add(i))}return e}_flushAllReleases(s){let e=new Set;for(let t of[...this._pendingReleases.values()]){let i=t.targetKey;i===s?(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer)):(this._runRelease(t),e.add(i))}return e}_targetsOverlap(s,e,t,i){return t!==void 0&&s===t?!0:!e||!i||e.deviceId!==i.deviceId?!1:!e.side||!i.side||e.side==="both"||i.side==="both"||e.side===i.side}_discardReleasesOverlapping(s,e){for(let t of[...this._pendingReleases.values()])!t.scopeGenerations.has(s)&&!this._targetsOverlap(t.targetKey,t.target,s,e)||(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer))}_discardAllReleases(){for(let s of this._pendingReleases.values())s.timer!==void 0&&this.timers.clearTimeout(s.timer);this._pendingReleases.clear()}endFromPointer(s,e,t,i){this._pointerId===null||e!==this._pointerId||t&&(i!==void 0&&this._stop!==i||this.end(s,i))}endActiveFromPointer(s,e){!this._motor||this._pointerId===null||this.endFromPointer(this._motor,s,e)}endKeyboard(s,e,t){this._pointerId!==null||!this._motor||s&&s.key!==this._key||e!==void 0&&this._stop!==e||t!==void 0&&this._keyboardKey!==null&&this._keyboardKey!==t||this.end(this._motor)}end(s,e){if(e!==void 0&&this._stop!==e||this._key!==s.key)return;let t=this._started,i=this._heldControl!==void 0,o={cover:this._cover??void 0,stopEntityId:this._stop??void 0};t&&i&&this._scheduleRelease(),this._reset(),!(!t||i)&&this._release(o)}cancel(s,e=!1){if(!s)return!1;let t=this._key===s.key;t&&this._reset();let i=!1;if(e)for(let o of[...this._pendingReleases.values()])o.motorKey===s.key&&(this._pendingReleases.delete(o.id),o.timer!==void 0&&this.timers.clearTimeout(o.timer),i=!0);return t||i}stopCover(s,e,t,i){let o=s.cover;if(!o)return;let r=[],l,c=new Map;if(this._key!==null&&(t==="side"||this._key===s.key)&&(o===this._cover||i!==void 0&&this._scopeStops.includes(i)||this._targetsOverlap(this._targetKey(),this._target,o,e))){let h=this._target?.side==="both"&&this._target.deviceId===e?.deviceId&&(e?.side==="left"||e?.side==="right")||i!==void 0&&this._remainingStops.includes(i);r=this._started&&h&&i?this._remainingStops.filter(_=>_!==i):[],l=this._pulseInFlight,c=new Map(r.map(_=>[_,this._stopTargetGenerations.get(_)??0])),h&&!this._heldControl&&r.length===0?this._repeatBlocked=!0:this._reset()}if(r.length>0){let h=()=>{for(let _ of r)this._stopTargetGenerations.get(_)===c.get(_)&&this.actions.stopBed(_)};l?l.then(h,h):h()}for(let h of[...this._pendingReleases.values()]){let _=h.target?.side==="both"&&h.target.deviceId===e?.deviceId&&(e?.side==="left"||e?.side==="right");t!=="side"&&_||t!=="side"&&h.motorKey!==s.key||!(h.cover===o||i!==void 0&&h.scopeGenerations.has(i)||this._targetsOverlap(h.targetKey,h.target,o,e))||(this._pendingReleases.delete(h.id),h.timer!==void 0&&this.timers.clearTimeout(h.timer))}}stopAll(s,e,t){let i=s??this._stop??void 0,o=this._key!==null&&this._started?{cover:this._cover??void 0,stopEntityId:this._stop??void 0}:void 0,r=typeof t=="object"?t:void 0,l=typeof t=="string"?t:void 0,c=[...new Set([...Array.isArray(e)?e:i?[i]:this._scopeStops,...this._targetScope(r),...i?[i]:[]])],h=e===!0&&!r,_=l===void 0||l===this._key||i===this._cover,m=this._key!==null&&_&&(h||c.length===0||this._scopeStops.some(y=>c.includes(y))||this._targetsOverlap(this._targetKey(),this._target,i,r));s!==void 0&&(h?this._discardAllReleases():this._discardReleasesOverlapping(s,r));let b=m&&this._started?this._remainingStops.filter(y=>!c.includes(y)):[],x=m?this._pulseInFlight:void 0,$=new Map(b.map(y=>[y,this._stopTargetGenerations.get(y)??0]));if(m&&this._reset(),s===void 0){let y=this._flushAllReleases(),v=o?.stopEntityId??o?.cover;o&&(v===void 0||!y.has(v))?this._release(o):!o&&y.size===0&&this.actions.stopBed(i)}else this.actions.stopBed(s);if(b.length>0){let y=()=>{for(let v of b)this._stopTargetGenerations.get(v)===$.get(v)&&this.actions.stopBed(v)};x?x.then(y,y):y()}}abandon(){let s=this._key===null?null:{cover:this._cover??void 0,stopEntityId:this._stop??void 0},e=this._started;this._reset(),s&&e&&this._release(s),this._flushAllReleases()}releaseOnFocusLoss(){this.abandon()}cancelForStopScope(s){let e=!1;for(let t of[...this._pendingReleases.values()])s.includes(t.targetKey)&&(this._pendingReleases.delete(t.id),t.timer!==void 0&&this.timers.clearTimeout(t.timer),e=!0);return this._key!==null&&this._scopeStops.some(t=>s.includes(t))&&(this._reset(),e=!0),e}_reset(){this._startTimer!==void 0&&this.timers.clearTimeout(this._startTimer),this._startTimer=void 0,this._key=null,this._motor=null,this._scopeStops=[],this._remainingStops=[],this._keyboardKey=null,this._pulseInFlight=void 0,this._cover=null,this._stop=null,this._target=void 0,this._pointerId=null,this._repeatBlocked=!1,this._started=!1,this._heldControl=void 0,this._generation++}};function yt(n,s,e){let t=()=>n.abandon(),i=()=>{s.visibilityState==="hidden"&&t()};return s.addEventListener("visibilitychange",i),e.addEventListener("pagehide",t),()=>{s.removeEventListener("visibilitychange",i),e.removeEventListener("pagehide",t)}}function we(n,s,e,t){n.stopAll(s,e??(s?[s]:void 0),t)}var xt={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","lighting.floor":"Floor light","lighting.mood":"Mood light","lighting.timer_pending":"Timer changes apply with the next floor-light command.","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status","card.both":"Both"};var $t={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","lighting.floor":"Gulvbelysning","lighting.mood":"Stemningslys","lighting.timer_pending":"Timerendringer brukes ved neste kommando for gulvbelysningen.","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus","card.both":"Begge"};var K={en:xt,nb:$t};function Qt(n){let s=(n?.locale?.language||n?.language||"en").toLowerCase(),e=s.split("-")[0];return K[s]?K[s]:K[e]?K[e]:e==="nn"||e==="no"?K.nb:K.en}function g(n,s,e){let i=Qt(n)[s]??K.en[s]??s;if(e)for(let[o,r]of Object.entries(e))i=i.replace(`{${o}}`,r);return i}var wt=["glance","quick","controls"];function kt(n,s){let e={...n,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:s==="glance"?"names":"angles",show_side_selector:!0,show_motors:s==="controls",show_lighting:!1,show_connection:!1,animate:!0};return s==="glance"?e.compact_actions=[]:delete e.compact_actions,e}function qe(n,s){return[...s.presets,...s.memory.flatMap(e=>e.goto?[e.goto]:[])].flatMap(e=>{let t=n.entities[e]?.translation_key;return t?[{key:X(t).key,entityId:e}]:[]})}function ke(n,s,e){let t=qe(n,s);if(e){let r=new Map(t.map(l=>[l.key,l]));return[...new Set(e)].flatMap(l=>{let c=r.get(l);return c?[c]:[]})}let i=t.find(r=>r.key==="preset_flat"),o=t.find(r=>r.key.startsWith("preset_memory_"))??t.find(r=>r!==i);return[i,o].filter(r=>r!==void 0)}function Se(n){return n.stop?[n.stop]:n.motors.flatMap(s=>s.cover?[s.cover]:[])}function Ee(n){if(!(!n||!n.startsWith("/")||/^\/[/\\]/.test(n)||/[\\\s]/.test(n)))return n}function Te(n,s){let e=pe(n,s),t=ee(n,e);return e&&t.length?[{key:"both",label:g(n,"card.both_sides"),bed:S(n,e)},...t.map(i=>({key:i,label:n.devices[i]?.name_by_user??n.devices[i]?.name??i,bed:S(n,i)}))]:he(n,s)?["both","left","right"].map(i=>({key:i,label:g(n,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:S(n,s,i)})):[{key:"both",label:g(n,"card.both_sides"),bed:S(n,s)}]}var St="4.2.4";function Et(n,s){return{graphic:mt(n,s),motors:n.motors.some(e=>e.cover||e.up||e.down)||!!n.stop||!!n.synchro,firmness:n.firmness.length>0,presets:n.presets.length>0,memory:n.memory.length>0,lighting:I(n.lights)||!!n.lights.state,massage:n.massage.buttons.length>0||n.massage.numbers.length>0||!!n.massage.states?.length||!!n.massage.selects?.length||!!n.massage.timer,utility:n.utility.length>0,climate:n.climate.entities.length>0||n.climate.selects.length>0||n.climate.numbers.length>0,connection:!!(n.connect||n.disconnect)}}var Zt="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",Xt="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",ei=(n,s)=>n.length===s.length&&n.every((e,t)=>e===s[t]),J=class extends C{constructor(){super(...arguments);this._computeLabel=e=>g(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!this.hass||!e)return;let t=Te(this.hass,e).map(r=>r.bed),i=t[0];if(!i)return;let o=new Map;for(let r of t)for(let l of r.memory){let c=o.get(l.slot);o.set(l.slot,{slot:l.slot,goto:c?.goto??l.goto,save:c?.save??l.save})}return{...i,memory:[...o.values()].sort((r,l)=>r.slot-l.slot)}}_presentKeys(e){let t=this.hass?Te(this.hass,this._config?.device_id).map(i=>i.bed):[e];return W.filter(i=>t.some(o=>Et(o,this.hass)[i]))}_orderedKeys(e){let t=this._presentKeys(e),o=(this._config?.section_order??[]).filter(l=>t.includes(l)),r=t.filter(l=>!o.includes(l));return[...o,...r]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=t&&this.hass?.states[t]?.attributes.friendly_name||`Memory ${e.slot}`,o=t&&this.hass?.entities[t]?.device_id,r=o?this.hass?.devices[o]:void 0,l=r?.name_by_user||r?.name;return l&&i.startsWith(`${l} `)?i.slice(l.length+1):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id!==t.device_id&&delete i.default_target,i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let o=this._orderedKeys(e),r=o.indexOf(t),l=r+i;if(r<0||l<0||l>=o.length)return;[o[r],o[l]]=[o[l],o[r]];let c=this._cfg;ei(o,this._presentKeys(e))?delete c.section_order:c.section_order=o,this._emit(c)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let o=this._memorySlots(e),r=this._config?.memory_slots,l=r&&r.length?r.map(Number):[...o];i?l.includes(t)||l.push(t):l=l.filter(h=>h!==t),l.sort((h,_)=>h-_);let c=this._cfg;l.length===o.length?delete c.memory_slots:c.memory_slots=l,this._emit(c)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?u`
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.sections")}</div>
        ${t.map((i,o)=>{let r=this._config?.[`show_${i}`]!==!1;return u`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${o===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title=${g(this.hass,"editor.move_up")}
                  aria-label=${g(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Zt}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${o===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title=${g(this.hass,"editor.move_down")}
                  aria-label=${g(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Xt}></path></svg>
                </button>
              </div>
              <span class="label">${g(this.hass,`editor.show_${i}`)}</span>
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
          ${g(this.hass,"editor.memory_group")}
        </div>
        ${i?u`<div class="row">
                <span class="label">${g(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:p}
        ${o?u`<div class="sub">
                <div class="sub-label">
                  ${g(this.hass,"editor.memory_slots")}
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
    `}_setOption(e,t){this._emit({...this._cfg,[e]:t})}_compactToggle(e,t){return u`<div class="row"><span class="label">${g(this.hass,e==="show_connection"?"editor.compact_connection":`editor.${e}`)}</span>
      <ha-switch .checked=${this._config?.[e]??t}
        @change=${i=>this._setOption(e,i.target.checked)}></ha-switch>
    </div>`}_compactGroup(){let e=this._config,t=Te(this.hass,e.device_id),i=t.find(c=>c.key===(e.default_target??"both")),o=t.flatMap(c=>qe(this.hass,c.bed)).filter((c,h,_)=>_.findIndex(m=>m.key===c.key)===h),r=e.compact_actions??(i?ke(this.hass,i.bed).map(c=>c.key):[]),l=[...r.filter(c=>o.some(h=>h.key===c)),...o.map(c=>c.key).filter(c=>!r.includes(c))];return u`
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        <label class="row"><span class="label">${g(this.hass,"editor.compact_labels")}</span>
          <select .value=${e.compact_labels??"angles"}
            @change=${c=>this._setOption("compact_labels",c.target.value)}>
            ${["angles","names","none"].map(c=>u`
              <option value=${c}>${g(this.hass,`editor.labels_${c}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        <label class="row path-row"><span class="label">${g(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${e.navigation_path??""} placeholder="/dashboard/bed"
            @change=${c=>this._setOption("navigation_path",c.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.compact_controls")}</div>
        ${t.length>1||!i?u`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${g(this.hass,"editor.default_target")}</span>
            <select .value=${e.default_target??"both"}
              @change=${c=>this._setOption("default_target",c.target.value)}>
              ${i?p:u`<option value=${e.default_target}>${g(this.hass,"compact.target_missing")}</option>`}
              ${t.map(c=>u`<option value=${c.key}>${c.label}</option>`)}
            </select>
          </label>`:p}
        ${this._compactToggle("show_motors",!1)}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${g(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${g(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${g(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${g(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${g(this.hass,"editor.labels_none")}</button>
        </div>
        ${l.map(c=>{let h=o.find($=>$.key===c),_=r.includes(c),m=r.indexOf(c),b=$=>{let y=[...r];[y[m],y[m+$]]=[y[m+$],y[m]],this._setOption("compact_actions",y)},x=this.hass.states[h.entityId];return u`<div class="row">
            <ha-checkbox .checked=${_} @change=${$=>this._setOption("compact_actions",$.target.checked?[...r,c]:r.filter(y=>y!==c))}></ha-checkbox>
            <span class="label">${x?.attributes.friendly_name??c}</span>
            <button class="icon-btn" ?disabled=${!_||m===0}
              aria-label=${g(this.hass,"editor.move_up")} @click=${()=>b(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!_||m===r.length-1}
              aria-label=${g(this.hass,"editor.move_down")} @click=${()=>b(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return u`<div class="group">
      <label class="row"><span class="label">${g(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${e=>this._setOption("layout",e.target.value)}>
          <option value="full">${g(this.hass,"editor.layout_full")}</option>
          <option value="compact">${g(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${g(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${wt.map(e=>u`
        <button @click=${()=>this._emit({...kt(this._config,e)})}>
          ${g(this.hass,`editor.recipe_${e}`)}
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
    `}};J.styles=ie`
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
  `,T([Y({attribute:!1})],J.prototype,"hass",2),T([B()],J.prototype,"_config",2);ue("adjustable-bed-card-editor",J);var ti=new Set(["back","legs","head","feet"]),A=class extends C{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._watched=[];this._compactStopTargets=new Map;this._hold=new xe({pulse:(e,t)=>Ie(this.hass,e,t),holdControl:(e,t)=>ft(this.hass,e,t),stopCover:(e,t)=>this._stopCompactTarget(e,t??e),stopBed:e=>{e&&this._stopCompactTarget(e)}});this._focusLossCleanup=null;this._windowPointerEnd=e=>{this._hold.endActiveFromPointer(e.pointerId,e.type==="pointercancel"||e.button===0)};this._windowKeyUp=e=>{(e.key==="Enter"||e.key===" ")&&this._hold.endKeyboard(void 0,void 0,e.key)};this._navigate=()=>{let e=Ee(this._config?.navigation_path);e&&(this._hold.abandon(),history.pushState(null,"",e),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))}}connectedCallback(){super.connectedCallback(),this._removeHoldLifecycle=yt(this._hold,document,window),window.addEventListener("pointerup",this._windowPointerEnd),window.addEventListener("pointercancel",this._windowPointerEnd),window.addEventListener("keyup",this._windowKeyUp),this._focusLossCleanup=bt(window,document,()=>document.visibilityState==="hidden",()=>this._hold.releaseOnFocusLoss())}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===L)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config&&(this._compactStopTargets.size>0?this._stopCompact():this._hold.abandon()),(e.device_id!==this._config?.device_id||e.default_target!==this._config?.default_target)&&(this._activePairedPane=e.default_target??"both"),this._config=e}getCardSize(){if(this._config?.layout!=="compact")return 8;let e=this._config;return Math.ceil((24+(e.show_header!==!1?36:0)+(e.show_graphic!==!1?150:0)+(e.compact_labels!=="none"?40:0)+(e.compact_actions?.length===0?0:110)+(e.show_motors===!0?180:0)+(e.show_lighting===!0?70:0)+(e.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){window.removeEventListener("pointerup",this._windowPointerEnd),window.removeEventListener("pointercancel",this._windowPointerEnd),window.removeEventListener("keyup",this._windowKeyUp),this._focusLossCleanup?.(),this._focusLossCleanup=null,this._removeHoldLifecycle?.(),this._removeHoldLifecycle=void 0,super.disconnectedCallback(),this._hold.abandon()}shouldUpdate(e){if(e.has("_config")||e.has("_saveModeFor")||e.has("_activePairedPane")||e.has("_synchronizingTo")||e.has("_synchronizationFailed")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities||t.devices!==this.hass.devices)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return p;if(!this._config.device_id)return this._notice("card.no_device");let e=pe(this.hass,this._config.device_id),t=ee(this.hass,e);if(e&&t.length)return this._renderPaired(e,t);if(this._config.device_id&&he(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=S(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),P(i)?this._notice("card.no_entities"):this._config.layout==="compact"?this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),bed:i}],!1):u`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(e,t="theme",i,o,r){let l=this._config,c={graphic:()=>l.show_graphic!==!1?i??this._graphic(e,t):p,motors:()=>l.show_motors!==!1?this._motors(e,o,r):p,firmness:()=>l.show_firmness!==!1?this._firmness(e):p,presets:()=>l.show_presets!==!1?this._presets(e):p,memory:()=>l.show_memory!==!1?this._memory(e):p,lighting:()=>l.show_lighting!==!1?this._lighting(e):p,massage:()=>l.show_massage!==!1?this._massage(e):p,utility:()=>l.show_utility!==!1?this._utility(e):p,climate:()=>l.show_climate!==!1?this._climate(e):p,connection:()=>l.show_connection!==!1?this._connection(e):p};return this._orderedSections().map(h=>c[h]?.()??p)}_renderPaired(e,t){let i=this.hass,o=S(i,e),r=t.map((m,b)=>({key:m,label:this._deviceLabel(m),bed:S(i,m),graphicTone:b===0?"left":"right",synchronizationTarget:{deviceId:m}})),l=r.flatMap(m=>m.bed.stop?[m.bed.stop]:[]),c=o.stop,h=[...new Set([...c?[c]:[],...l])],_=[{key:"both",label:g(i,"card.both_sides"),bed:o,stopScope:h,remainingStopIds:l},...r.map(m=>({...m,stopScope:m.bed.stop?[m.bed.stop]:[]}))];return this._watched=[o,...r.map(m=>m.bed)].flatMap(m=>this._collectWatched(m)),P(o)&&r.every(m=>P(m.bed))?this._notice("card.no_entities"):this._renderPairedCard(e,_)}_renderSingleAddressPaired(e){let t=this.hass,i={both:S(t,e,"both"),left:S(t,e,"left"),right:S(t,e,"right")},o=[i.left.stop,i.right.stop].filter(r=>r!==void 0);return this._watched=Object.values(i).flatMap(r=>this._collectWatched(r)),Object.values(i).every(r=>P(r))?this._notice("card.no_entities"):this._renderPairedCard(e,[{key:"both",label:g(t,"card.both_sides"),bed:i.both,stopScope:[...new Set([i.both.stop,...o].filter(r=>r!==void 0))],remainingStopIds:o},{key:"left",label:g(t,"card.left_side"),bed:i.left,graphicTone:"left",stopScope:i.left.stop?[i.left.stop]:[],synchronizationTarget:{deviceId:e,side:"left"}},{key:"right",label:g(t,"card.right_side"),bed:i.right,graphicTone:"right",stopScope:i.right.stop?[i.right.stop]:[],synchronizationTarget:{deviceId:e,side:"right"}}])}_renderPairedCard(e,t){if(this._config?.layout==="compact")return this._renderCompact(e,t,!0);let i=t.filter(c=>!P(c.bed)),o=i.find(c=>c.key===this._activePairedPane)??i[0],r=i.filter(c=>c.key!=="both"),l=o.key==="both";return u`
      <ha-card class="paired-card">
        ${this._header(o.bed,e)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(c=>u`
              <button
                class="pane-tab side-${c.graphicTone??"theme"} ${c.key===o.key?"active":""}"
                role="tab"
                aria-selected=${c.key===o.key?"true":"false"}
                @click=${()=>this._selectPairedPane(c.key)}
              >
                ${c.graphicTone?u`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span>${c.key==="both"?g(this.hass,"card.both"):c.label}</span>
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${o.label}>
          ${this._renderSections(o.bed,o.graphicTone,l?this._pairedOverview(r):void 0,o.stopScope,o.remainingStopIds)}
          ${l&&this._config?.show_lighting!==!1?this._combinedLighting(o.bed,r):p}
          ${l&&this._config?.show_connection!==!1?this._combinedBluetooth(r):p}
        </div>
      </ha-card>
    `}_renderCompact(e,t,i){let o=this._config,r=t.find(v=>v.key===this._activePairedPane),l=r?.bed,c=l?ke(this.hass,l,o.compact_actions):[],h=o.show_motors===!0&&l?l.motors.filter(v=>v.cover||v.up||v.down||v.position):[],_=c.length>0||h.length>0||o.show_lighting===!0,m=o.compact_actions?.length!==0||o.show_motors===!0||o.show_lighting===!0,b=i?t.filter(v=>v.key!=="both"):t,x=!!l&&Se(l).length>0,$=c.length>0||h.length>0,y=Ee(o.navigation_path);return u`
      <ha-card class="compact-card ${m?"":"compact-glance"} ${o.animate===!1?"no-animation":""}">
        ${o.show_header!==!1?u`
          <div class="compact-header">
            <span class="title">${this._title(e)}</span>
            ${y?u`<button class="compact-open" @click=${this._navigate}
              aria-label=${g(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:p}
          </div>`:p}
        ${i&&m?o.show_side_selector!==!1?u`
          <div class="pane-tabs compact-tabs" role="group"
            style=${`--pane-count:${t.filter(v=>!P(v.bed)).length}`}
            aria-label=${g(this.hass,"compact.target")}>
            ${t.filter(v=>!P(v.bed)).map(v=>u`
              <button class="pane-tab side-${v.graphicTone??"theme"} ${v.key===r?.key?"active":""}"
                aria-pressed=${v.key===r?.key?"true":"false"}
                title=${v.label}
                @click=${()=>this._selectPairedPane(v.key)}>
                ${v.graphicTone?u`<span class="dual-swatch" aria-hidden="true"></span>`:p}
                <span class="compact-tab-label">${v.key==="both"?g(this.hass,"card.both"):v.label}</span>
              </button>`)}
          </div>`:u`<div class="compact-target">
            ${g(this.hass,"compact.target")}: ${r?.label??g(this.hass,"compact.target_missing")}
          </div>`:p}
        ${o.show_graphic!==!1?this._compactGraphic(b):p}
        ${this._compactReadouts(b)}
        ${!r&&m?u`<div class="hint" role="status">
          ${g(this.hass,"compact.target_missing")}</div>`:p}
        ${h.length?u`<div class="rows compact-motors">
          ${h.map(v=>v.cover||v.up||v.down?this._motorRow(v,l?.stop,!0,r?.stopScope,r?.remainingStopIds):this._moreInfoRow(v.position))}
        </div>`:p}
        ${c.length||$||this._compactStopTargets.size?u`
          <div class="tiles compact-actions">
            ${c.map(({entityId:v})=>u`<button class="tile"
              ?disabled=${!x||!this._available(v)}
              @click=${()=>this._compactRecall(v,l)}>
              ${this._icon(v)}<span class="tile-label">${this._name(v)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!x&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(l)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${g(this.hass,"action.stop")}</span>
            </button>
          </div>`:p}
        ${o.show_lighting===!0&&l?u`
          ${this._lighting(l)}
          ${i&&r?.key==="both"?this._combinedLighting(l,b):p}
        `:p}
        ${o.show_connection===!0?i&&r?.key==="both"?this._combinedBluetooth(b):u`<div class="compact-connections">
          ${b.map(v=>{let f=this._connectionStatus(v.bed);return f?u`<span>${this._connectionDot(v.bed)}
              ${v.label}: ${g(this.hass,`status.${f}`)}</span>`:p})}
        </div>`:p}
        ${!_&&o.show_graphic===!1&&o.compact_labels==="none"&&o.show_header===!1&&o.show_connection!==!0?u`<div class="hint">${this._title(e)}</div>`:p}
      </ha-card>`}_compactGraphic(e){let t=e.map(h=>this._graphicState(h.bed)),i=t[0],o=t[1],r=t.length>0&&t.every(h=>h!==void 0),l=e.map((h,_)=>`${h.label}: ${t[_]?this._positionSummary(t[_]):g(this.hass,"compact.no_position")}`).join(". "),c=r&&i?o?Ue({left:i,right:o}):Ge({...i,upper:{angle:i.upper.angle},lower:{angle:i.lower.angle}}):u`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${g(this.hass,"compact.no_position")}</span></div>`;return Ee(this._config?.navigation_path)?u`<button class="compact-graphic" @click=${this._navigate}
          aria-label="${g(this.hass,"compact.open")}. ${l}">${c}</button>`:u`<div class="compact-graphic" role="img" aria-label=${l}>${c}</div>`}_compactReadouts(e){let t=this._config?.compact_labels??"angles";return t==="none"?p:u`<div class="compact-readouts ${t==="names"?"compact-names":""}">
      ${e.map(i=>u`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name" title=${i.label}>
          <span class="dual-swatch" aria-hidden="true"></span>
          <span aria-label=${i.label}>${t==="angles"&&e.length>1?[...i.label][0]:i.label}</span>
        </span>
        ${t==="angles"?u`<span class="compact-position"
          title=${i.bed.motors.map(o=>`${this._motorName(o)} ${this._readout(o)??"?"}`).join(" \xB7 ")}
        >${i.bed.motors.filter(o=>o.angle||o.position||o.cover).map(o=>this._readout(o)??"?").join(" / ")||g(this.hass,"compact.no_position")}</span>`:p}
      </div>`)}
    </div>`}_available(e){let t=this._state(e)?.state;return t!==void 0&&t!=="unavailable"}_compactRecall(e,t){this._hold.abandon(),Se(t).forEach(i=>this._compactStopTargets.set(i,Symbol())),this._press(e),this.requestUpdate()}_stopCompact(e){let t=[...new Set([...e?Se(e):[],...this._compactStopTargets.keys()])];this._hold.cancelForStopScope(t);for(let i of t)this._compactStopTargets.has(i)||this._compactStopTargets.set(i,Symbol());for(let i of this._compactStopTargets.keys())this._stopCompactTarget(i);this._compactStopTargets.size&&this.requestUpdate()}_stopCompactTarget(e,t=e){let i=this._compactStopTargets.get(t),o=e.startsWith("cover.");this.hass?.callService(o?"cover":"button",o?"stop_cover":"press",{entity_id:e}).then(()=>{i!==void 0&&this._compactStopTargets.get(t)===i&&(this._compactStopTargets.delete(t),this.requestUpdate())}).catch(()=>{})}_selectPairedPane(e){this._activePairedPane!==e&&(this._activePairedPane=e,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(e){if(!e.connectivity)return;let t=this._state(e.connectivity);return t?.attributes?.state_detail==="connecting"?"connecting":t?.state==="on"?"connected":t?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(e){let t=this._connectionStatus(e);return t?u`<span
      class="connection-dot ${t}"
      title=${g(this.hass,`status.${t}`)}
    ></span>`:p}_pairedOverview(e){let t=e.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(t.length<2)return p;let[i,o]=t;return u`
      <div class="graphic dual-graphic">
        ${Ue({left:i.graphic,right:o.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,o].map(({pane:r,graphic:l},c)=>u`
            <div class="dual-readout side-${c===0?"left":"right"}">
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
        <span class="dual-sync-label">${g(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${g(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(e,t,"left")}
          >
            ${this._synchronizingTo==="left"?u`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:u`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${g(this.hass,"sync.label")} ${t.label}"
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
            <span>${g(this.hass,"sync.incomplete")}</span>
          </div>`:p}
    `}_synchronizationPlan(e,t){let i=new Map(t.motors.map(l=>[l.key,l])),o=e.motors.filter(l=>ti.has(l.key)&&i.has(l.key)&&this._hasPositionFeedback(l)&&this._hasPositionFeedback(i.get(l.key)));if(o.length===0)return[];let r=o.map(l=>({motor:l.key,position:this._angle(l)}));return r.some(l=>l.position===void 0)||o.some(l=>this._angle(i.get(l.key))===void 0)?[]:r}_hasPositionFeedback(e){return e.angle!==void 0||e.position!==void 0}async _synchronizePositions(e,t,i){if(this._synchronizingTo||!this.hass)return;let o=i==="left"?e:t,r=i==="left"?t:e,l=r.synchronizationTarget;if(!l)return;let c=this._synchronizationPlan(o.bed,r.bed);if(c.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(L,"set_positions",{device_id:[l.deviceId],positions:c,...l.side?{side:l.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(e){return(e.upperMotor===e.lowerMotor?[e.upperMotor]:[e.upperMotor,e.lowerMotor]).map(i=>{let o=this._readout(i);return o?`${this._motorName(i)} ${o}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(e,t){if(this._hasLighting(e))return p;let i=t.map(_=>this._mainLight(_.bed)).filter(_=>_!==void 0);if(i.length===0)return p;let o=i.filter(_=>this._state(_)?.state==="on").length,r=o===i.length,l=o>0,c=r?"combined.on":l?"combined.mixed":"combined.off",h=g(this.hass,"combined.lights");return u`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${l?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${h}</span>
          <span class="secondary">${g(this.hass,c)}</span>
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
        ${t.map(({pane:i,entityId:o})=>{let r=this._connectionStatus(i.bed),c=this._state(o)?.attributes.rssi;return u`
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
                  ${g(this.hass,`status.${r}`)}${typeof c=="number"?` \xB7 ${c} dBm`:""}
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
    `}_mainLight(e){return e.lights.light??e.lights.switch}_hasLighting(e){return I(e.lights)}_deviceLabel(e){let t=this.hass?.devices[e];return t?.name_by_user??t?.name??e}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...W];let t=new Set(W),i=e.filter(r=>t.has(r)),o=W.filter(r=>!i.includes(r));return[...i,...o]}_header(e,t){let i=this._connectionStatus(e),o={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return u`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(t)}</span>
        ${i===void 0?p:u`
                <button
                  class="conn ${o[i].cls}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${g(this.hass,o[i].key)}
                >
                  <ha-icon icon=${o[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e,t="theme"){let i=this._graphicState(e);return i?u`
      <div class="graphic">
        ${Ge(i,t)}
      </div>
    `:p}_graphicState(e){let t=e.motors.filter(c=>{let h=c.angle??c.position;return h!==void 0&&this._state(h)?.attributes.unit_of_measurement==="\xB0"});if(t.length===0||t.some(c=>this._angle(c)===void 0))return;let i=We(t);if(!i)return;let{upper:o,lower:r}=i,l=e.motors.some(c=>{let h=c.cover?this._state(c.cover)?.state:void 0;return h==="opening"||h==="closing"});return{upperMotor:o,lowerMotor:r,upper:{label:this._motorName(o),angle:this._angle(o)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:l}}_motors(e,t,i){let o=t??(e.stop?[e.stop]:[]),r=e.motors.filter(h=>h.cover||h.up||h.down),l=e.motors.filter(h=>h.position&&!h.cover&&!h.up&&!h.down);if(r.length===0&&l.length===0&&!e.synchro&&!e.controlSide&&!e.stop)return p;let c=r.length>0||l.length>0||!!e.synchro||!!e.controlSide;return u`
      ${c?this._heading("section.position"):p}
      ${e.controlSide?this._moreInfoRow(e.controlSide):p}
      ${e.synchro?this._toggleRow(e.synchro):p}
      ${r.length?u`<div class="rows">
              ${r.map(h=>this._motorRow(h,e.stop,!1,o,i))}
            </div>`:p}
      ${l.length?u`<div class="rows">
              ${l.map(h=>this._moreInfoRow(h.position))}
            </div>`:p}
      ${e.stop?u`<button class="stop-all" @click=${()=>we(this._hold,e.stop,o)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${g(this.hass,"action.stop_all")}</span>
            </button>`:p}
    `}_firmness(e){return e.firmness.length===0?p:u`
      ${this._heading("section.firmness")}
      <div class="rows">${e.firmness.map(t=>this._moreInfoRow(t))}</div>
    `}_motorRow(e,t,i=!1,o,r){let l=this._readout(e),c=!!e.cover||!!t,h=u`
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
            aria-label=${g(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e,t,o)}
            ?disabled=${!c}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>`}
          ${i?p:this._motorDirection(e,"down",t,o,r)}
        </div>
      </div>
    `}_motorDirection(e,t,i,o,r){let l=e.cover??e[t],c=!!e.cover||!!i;return u`
      <button class="cg-btn"
        aria-label=${g(this.hass,`action.${t}`)}
        @pointerdown=${h=>this._startHold(h,e,t,i,o,r)}
        @pointerup=${h=>this._endPointerHold(h,e,i)}
        @pointercancel=${h=>this._endPointerHold(h,e,i)}
        @keydown=${h=>this._startHold(h,e,t,i,o,r)}
        @keyup=${h=>this._endKeyHold(h,e,i)}
        @click=${h=>this._activateWithoutPointer(h,e,t,i,o)}
        ?disabled=${!l||this._config?.layout==="compact"&&(!c||!this._available(l))}
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
    `}_actionTile(e,t,i=()=>this._press(e)){let o=_t(this.hass,e);return o?this._heldActionTile(e,o,t):this._tile(e,i)}_heldActionTile(e,t,i){return u`<button class="tile"
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
    </button>`}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let c=new Set(i.map(Number));t=t.filter(h=>c.has(h.slot))}if(t.length===0)return p;let o=this._config?.memory_save!==!1&&t.some(c=>c.save),r=t.map(c=>c.save??c.goto??String(c.slot)).join("|"),l=this._saveModeFor===r;return u`
      <div class="section-heading heading-row">
        <span>${g(this.hass,"section.memory")}</span>
        ${o?u`<button
                class="set-btn ${l?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${l?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${g(this.hass,l?"memory.cancel":"memory.set")}</span>
              </button>`:p}
      </div>
      ${l?u`<div class="hint">${g(this.hass,"memory.set_hint")}</div>`:p}
      <div class="tiles">${t.map(c=>this._memoryTile(c,l,e.stop))}</div>
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
      ${t.level?this._moreInfoRow(t.level):p}
      ${t.numbers?.map(r=>this._moreInfoRow(r))}
      ${t.timer?this._moreInfoRow(t.timer):p}
      ${t.timerMinutes?this._moreInfoRow(t.timerMinutes):p}
      ${!t.timerAppliesImmediately&&(t.timerMinutes||t.timerToggle)?u`<div class="hint">${g(this.hass,"lighting.timer_pending")}</div>`:p}
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
    `}_heading(e){return u`<div class="section-heading">${g(this.hass,e)}</div>`}_subheading(e){return u`<div class="lighting-heading">${g(this.hass,e)}</div>`}_tile(e,t,i={}){return u`
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
      ></ha-state-icon>`:u`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return u`<ha-card><div class="notice">${g(this.hass,e)}</div></ha-card>`}_state(e){return this.hass?.states[e]}_title(e){return this._config?.name?this._config.name:this._deviceName(e)??g(this.hass,"card.default_name")}_deviceName(e=this._config?.device_id){let t=e?this.hass?.devices[e]:void 0;return t?.name_by_user||t?.name||void 0}_name(e){let t=this._state(e)?.attributes.friendly_name??this.hass?.entities[e]?.name??e,i=this.hass?.entities[e]?.device_id,o=this._deviceName(i);return o&&t.startsWith(o+" ")?t.slice(o.length+1):t}_motorName(e){let t=`motor.${e.key}`,i=g(this.hass,t);return i!==t?i:e.key.split("_").map(o=>o.charAt(0).toUpperCase()+o.slice(1)).join(" ")}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){let t=e.angle??e.position;if(t){let i=this._angle(e);if(i===void 0)return;let o=this._state(t)?.attributes.unit_of_measurement,r=e.angle?"\xB0":"%";return`${Math.round(i)}${typeof o=="string"?o:r}`}if(e.cover){let i=this._state(e.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(o=>o&&t.add(o));e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(o=>o&&t.add(o));return[e.stop,e.synchro,e.controlSide,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.state,e.lights.level,e.lights.toggle,e.lights.cycle,e.lights.timer,e.lights.timerMinutes,e.lights.timerToggle,e.lights.mood?.toggle,e.massage.timer].forEach(i=>i&&t.add(i)),e.firmness.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.lights.buttons?.forEach(i=>t.add(i)),e.lights.numbers?.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.massage.selects?.forEach(i=>t.add(i)),e.massage.states?.forEach(i=>t.add(i)),e.lights.mood?.selects.forEach(i=>t.add(i)),e.lights.mood?.numbers.forEach(i=>t.add(i)),e.lights.mood?.buttons?.forEach(i=>t.add(i)),e.utility.forEach(i=>t.add(i)),e.utilityNumbers?.forEach(i=>t.add(i)),e.utilitySelects?.forEach(i=>t.add(i)),e.utilityStates?.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),e.climate.numbers.forEach(i=>t.add(i)),[...t]}_startHold(e,t,i,o,r,l){let c=null;if(e instanceof KeyboardEvent){if(e.repeat||e.key!=="Enter"&&e.key!==" ")return;e.preventDefault()}else{if(e.button!==0||!e.isPrimary)return;e.currentTarget.setPointerCapture?.(e.pointerId),e.preventDefault(),c=e.pointerId}this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):t.cover&&this._compactStopTargets.set(t.cover,Symbol()),this.requestUpdate()),this._hold.start(t,i,c,o,r??(o?[o]:[]),l,e instanceof KeyboardEvent?e.key:null,$e(this.hass,o??t.holdEntityId??t.cover??t[i]))}_activateWithoutPointer(e,t,i,o,r){e.detail!==0||this._hold.heldKey!==null||(this._config?.layout==="compact"&&(o?this._compactStopTargets.set(o,Symbol()):t.cover&&this._compactStopTargets.set(t.cover,Symbol()),this.requestUpdate()),this._hold.claimStopScope([...r??[],...o?[o]:[],...t.cover?[t.cover]:[]],$e(this.hass,o??t.holdEntityId??t.cover??t[i])),vt(this.hass,t,i))}_endPointerHold(e,t,i){this._hold.endFromPointer(t,e.pointerId,e.type!=="pointerup"||e.button===0,i)}_endKeyHold(e,t,i){e.key!=="Enter"&&e.key!==" "||(e.stopPropagation(),this._hold.endKeyboard(t,i,e.key))}_endHold(e,t){this._hold.end(e,t)}_motorStop(e,t,i){if(e.cover){i?.length?we(this._hold,e.cover,[...i,e.cover],e.coverStopScope==="side"?void 0:e.key):(this._hold.stopCover(e,$e(this.hass,e.cover),e.coverStopScope??"motor",t),this._cover(e.cover,"stop_cover"));return}we(this._hold,t,i)}_toggleSaveMode(e){this._saveModeFor=this._saveModeFor===e?void 0:e}_saveMemory(e){e.save&&this._press(e.save),this._saveModeFor=void 0}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_setEntities(e,t){this.hass?.callService("homeassistant",t?"turn_on":"turn_off",{entity_id:e})?.catch(()=>{})}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};A.styles=ie`
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
  `,T([Y({attribute:!1})],A.prototype,"hass",2),T([B()],A.prototype,"_config",2),T([B()],A.prototype,"_saveModeFor",2),T([B()],A.prototype,"_activePairedPane",2),T([B()],A.prototype,"_synchronizingTo",2),T([B()],A.prototype,"_synchronizationFailed",2);ue("adjustable-bed-card",A);console.info(`%c adjustable-bed-card %c ${St} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{A as AdjustableBedCard};
