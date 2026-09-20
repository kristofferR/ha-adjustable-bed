/* adjustable-bed-card 4.0.0 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var re=Object.defineProperty;var ae=Object.getOwnPropertyDescriptor;var x=(n,o,t,e)=>{for(var i=e>1?void 0:e?ae(o,t):o,s=n.length-1,r;s>=0;s--)(r=n[s])&&(i=(e?r(o,t,i):r(i))||i);return e&&i&&re(o,t,i),i};var T="adjustable_bed";function F(n){for(let o of["left","right","both"]){let t=`_${o}`;if(n.endsWith(t))return{key:n.slice(0,-t.length),side:o}}return{key:n}}var N=["graphic","motors","firmness","presets","memory","lighting","massage","utility","climate","connection"],Bt=["back","legs","back_legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],gt=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_swing","preset_incline","preset_both_up","preset_yoga"],ce=n=>n.split(".",1)[0],mt=n=>n.translation_key??"";function le(){return{motors:[],firmness:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[]},utility:[]}}function y(n,o,t){let e=le();if(!o||!n?.entities)return e;let i=n.devices?.[o]?.parent_device_id||Object.values(n.devices??{}).some(g=>g.parent_device_id===o),s=new Map,r=g=>{let u=s.get(g);return u||(u={key:g},s.set(g,u)),u},a=new Map,c=new Map,p=g=>{let u=c.get(g);return u||(u={slot:g},c.set(g,u)),u};for(let g of Object.values(n.entities)){if(g.device_id!==o||g.platform!==T||g.hidden)continue;let u=g.entity_id,$=ce(u),v=mt(g);if(!v)continue;let E=F(v),ne=n.states[u]?.attributes.bed_side??n.states[u]?.attributes.side??E.side;if(t&&ne!==t)continue;let m=t||i?E.key:v,P;switch($){case"cover":r(m).cover=u;break;case"sensor":m.endsWith("_angle")&&(r(m.slice(0,-6)).angle=u);break;case"number":m.endsWith("_position")?r(m.slice(0,-9)).position=u:!t&&E.side&&E.key.endsWith("_position")?r(`${E.key.slice(0,-9)}_${E.side}`).position=u:m.startsWith("massage_")&&m.endsWith("_intensity")?e.massage.numbers.push(u):m==="light_level"?e.lights.level=u:m.startsWith("sleep_number_setting")&&e.firmness.push(u);break;case"button":gt.includes(m)||m.startsWith("preset_")?(P=m.match(/^preset_memory_(\d+)$/))?p(Number(P[1])).goto=u:a.set(m,u):(P=m.match(/^program_memory_(\d+)$/))?p(Number(P[1])).save=u:m==="stop"||m==="stop_both"?e.stop=u:m==="connect"?e.connect=u:m==="disconnect"?e.disconnect=u:m==="toggle_light"?e.lights.toggle=u:m==="light_cycle"?e.lights.cycle=u:m==="sync_positions"||m==="child_lock_toggle"||m==="auxiliary_action"||m==="remote_action"||m==="solace_music_toggle"||m==="solace_music_off"||m==="wake_controller"||m==="reset_defaults"||m==="factory_reset"?e.utility.push(u):m.startsWith("massage_")?e.massage.buttons.push(u):(P=m.match(/^(.+)_(up|down)$/))&&(r(P[1])[P[2]]=u);break;case"switch":m==="under_bed_lights"?e.lights.switch=u:m==="synchro_mode"?e.synchro=u:(m==="linak_automatic_drive"||m==="automatic_light")&&e.utility.push(u);break;case"light":e.lights.light=u;break;case"binary_sensor":m==="ble_connection"?e.connectivity=u:m==="under_bed_lights"?e.lights.state=u:m.startsWith("bed_presence")&&e.presence.push(u);break;case"select":m==="light_timer"?e.lights.timer=u:m==="massage_timer"?e.massage.timer=u:/thermal|footwarming|foundation/.test(m)&&e.climate.selects.push(u);break;case"climate":e.climate.entities.push(u);break}}let _=[...s.keys()],f=[...Bt.filter(g=>s.has(g)),..._.filter(g=>!Bt.includes(g)).sort()];e.motors=f.map(g=>s.get(g)).filter(g=>g.cover||g.up||g.down||g.angle||g.position);let b=[...a.keys()];return e.presets=[...gt.filter(g=>a.has(g)),...b.filter(g=>!gt.includes(g)).sort()].map(g=>a.get(g)),e.memory=[...c.values()].filter(g=>g.goto||g.save).sort((g,u)=>g.slot-u.slot),e}function tt(n,o){return!o||!n?.entities?!1:Object.values(n.entities).some(t=>t.device_id===o&&t.platform===T&&(n.states[t.entity_id]?.attributes.bed_side==="both"||F(mt(t)).side==="both"))}function K(n,o){if(!o||!n?.devices)return[];let t=i=>{let s=n.devices[i];return(s?.name_by_user??s?.name??i).toLowerCase()},e=i=>{for(let s of Object.values(n.entities??{})){if(s.device_id!==i||s.platform!=="adjustable_bed")continue;let r=n.states[s.entity_id]?.attributes.bed_side??F(mt(s)).side;if(r==="left")return 0;if(r==="right")return 1}return 2};return Object.values(n.devices).filter(i=>(i.parent_device_id??i.via_device_id)===o).map(i=>i.id).sort((i,s)=>e(i)-e(s)||t(i).localeCompare(t(s)))}function et(n,o){if(!o||!n?.devices)return o;let t=n.devices[o]?.parent_device_id??n.devices[o]?.via_device_id;return t&&n.devices[t]&&K(n,t).length?t:o}function M(n){let o=n.lights;return n.motors.length===0&&!n.synchro&&n.firmness.length===0&&n.presets.length===0&&n.memory.length===0&&!n.stop&&!n.connect&&!n.disconnect&&!n.connectivity&&!o.light&&!o.switch&&!o.state&&!o.level&&!o.toggle&&!o.cycle&&!o.timer&&n.massage.buttons.length===0&&n.massage.numbers.length===0&&!n.massage.timer&&n.climate.entities.length===0&&n.climate.selects.length===0&&n.utility.length===0}var ft="adjustable-bed-card",Ht={type:ft,name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed",getEntitySuggestion:(n,o)=>{let t=n.entities[o];return t?.platform!==T||!t.device_id?null:{config:{type:`custom:${ft}`,device_id:t.device_id}}}};function de(n){let o=n.customCards??=[],t=o.findIndex(e=>e.type===ft);t===-1?o.push(Ht):o[t]=Ht}typeof window<"u"&&de(window);var it=globalThis,ot=it.ShadowRoot&&(it.ShadyCSS===void 0||it.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,_t=Symbol(),zt=new WeakMap,I=class{constructor(o,t,e){if(this._$cssResult$=!0,e!==_t)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=o,this.t=t}get styleSheet(){let o=this.o,t=this.t;if(ot&&o===void 0){let e=t!==void 0&&t.length===1;e&&(o=zt.get(t)),o===void 0&&((this.o=o=new CSSStyleSheet).replaceSync(this.cssText),e&&zt.set(t,o))}return o}toString(){return this.cssText}},Ot=n=>new I(typeof n=="string"?n:n+"",void 0,_t),W=(n,...o)=>{let t=n.length===1?n[0]:o.reduce((e,i,s)=>e+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[s+1],n[0]);return new I(t,n,_t)},jt=(n,o)=>{if(ot)n.adoptedStyleSheets=o.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of o){let e=document.createElement("style"),i=it.litNonce;i!==void 0&&e.setAttribute("nonce",i),e.textContent=t.cssText,n.appendChild(e)}},vt=ot?n=>n:n=>n instanceof CSSStyleSheet?(o=>{let t="";for(let e of o.cssRules)t+=e.cssText;return Ot(t)})(n):n;var{is:pe,defineProperty:he,getOwnPropertyDescriptor:ue,getOwnPropertyNames:ge,getOwnPropertySymbols:me,getPrototypeOf:fe}=Object,st=globalThis,Nt=st.trustedTypes,_e=Nt?Nt.emptyScript:"",ve=st.reactiveElementPolyfillSupport,q=(n,o)=>n,V={toAttribute(n,o){switch(o){case Boolean:n=n?_e:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,o){let t=n;switch(o){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},nt=(n,o)=>!pe(n,o),Lt={attribute:!0,type:String,converter:V,reflect:!1,useDefault:!1,hasChanged:nt};Symbol.metadata??=Symbol("metadata"),st.litPropertyMetadata??=new WeakMap;var S=class extends HTMLElement{static addInitializer(o){this._$Ei(),(this.l??=[]).push(o)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(o,t=Lt){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(o)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(o,t),!t.noAccessor){let e=Symbol(),i=this.getPropertyDescriptor(o,e,t);i!==void 0&&he(this.prototype,o,i)}}static getPropertyDescriptor(o,t,e){let{get:i,set:s}=ue(this.prototype,o)??{get(){return this[t]},set(r){this[t]=r}};return{get:i,set(r){let a=i?.call(this);s?.call(this,r),this.requestUpdate(o,a,e)},configurable:!0,enumerable:!0}}static getPropertyOptions(o){return this.elementProperties.get(o)??Lt}static _$Ei(){if(this.hasOwnProperty(q("elementProperties")))return;let o=fe(this);o.finalize(),o.l!==void 0&&(this.l=[...o.l]),this.elementProperties=new Map(o.elementProperties)}static finalize(){if(this.hasOwnProperty(q("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(q("properties"))){let t=this.properties,e=[...ge(t),...me(t)];for(let i of e)this.createProperty(i,t[i])}let o=this[Symbol.metadata];if(o!==null){let t=litPropertyMetadata.get(o);if(t!==void 0)for(let[e,i]of t)this.elementProperties.set(e,i)}this._$Eh=new Map;for(let[t,e]of this.elementProperties){let i=this._$Eu(t,e);i!==void 0&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(o){let t=[];if(Array.isArray(o)){let e=new Set(o.flat(1/0).reverse());for(let i of e)t.unshift(vt(i))}else o!==void 0&&t.push(vt(o));return t}static _$Eu(o,t){let e=t.attribute;return e===!1?void 0:typeof e=="string"?e:typeof o=="string"?o.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(o=>this.enableUpdating=o),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(o=>o(this))}addController(o){(this._$EO??=new Set).add(o),this.renderRoot!==void 0&&this.isConnected&&o.hostConnected?.()}removeController(o){this._$EO?.delete(o)}_$E_(){let o=new Map,t=this.constructor.elementProperties;for(let e of t.keys())this.hasOwnProperty(e)&&(o.set(e,this[e]),delete this[e]);o.size>0&&(this._$Ep=o)}createRenderRoot(){let o=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return jt(o,this.constructor.elementStyles),o}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(o=>o.hostConnected?.())}enableUpdating(o){}disconnectedCallback(){this._$EO?.forEach(o=>o.hostDisconnected?.())}attributeChangedCallback(o,t,e){this._$AK(o,e)}_$ET(o,t){let e=this.constructor.elementProperties.get(o),i=this.constructor._$Eu(o,e);if(i!==void 0&&e.reflect===!0){let s=(e.converter?.toAttribute!==void 0?e.converter:V).toAttribute(t,e.type);this._$Em=o,s==null?this.removeAttribute(i):this.setAttribute(i,s),this._$Em=null}}_$AK(o,t){let e=this.constructor,i=e._$Eh.get(o);if(i!==void 0&&this._$Em!==i){let s=e.getPropertyOptions(i),r=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:V;this._$Em=i;let a=r.fromAttribute(t,s.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(o,t,e,i=!1,s){if(o!==void 0){let r=this.constructor;if(i===!1&&(s=this[o]),e??=r.getPropertyOptions(o),!((e.hasChanged??nt)(s,t)||e.useDefault&&e.reflect&&s===this._$Ej?.get(o)&&!this.hasAttribute(r._$Eu(o,e))))return;this.C(o,t,e)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(o,t,{useDefault:e,reflect:i,wrapped:s},r){e&&!(this._$Ej??=new Map).has(o)&&(this._$Ej.set(o,r??t??this[o]),s!==!0||r!==void 0)||(this._$AL.has(o)||(this.hasUpdated||e||(t=void 0),this._$AL.set(o,t)),i===!0&&this._$Em!==o&&(this._$Eq??=new Set).add(o))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let o=this.scheduleUpdate();return o!=null&&await o,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,s]of this._$Ep)this[i]=s;this._$Ep=void 0}let e=this.constructor.elementProperties;if(e.size>0)for(let[i,s]of e){let{wrapped:r}=s,a=this[i];r!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,s,a)}}let o=!1,t=this._$AL;try{o=this.shouldUpdate(t),o?(this.willUpdate(t),this._$EO?.forEach(e=>e.hostUpdate?.()),this.update(t)):this._$EM()}catch(e){throw o=!1,this._$EM(),e}o&&this._$AE(t)}willUpdate(o){}_$AE(o){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(o)),this.updated(o)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(o){return!0}update(o){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(o){}firstUpdated(o){}};S.elementStyles=[],S.shadowRootOptions={mode:"open"},S[q("elementProperties")]=new Map,S[q("finalized")]=new Map,ve?.({ReactiveElement:S}),(st.reactiveElementVersions??=[]).push("2.1.2");var Et=globalThis,Dt=n=>n,rt=Et.trustedTypes,Ut=rt?rt.createPolicy("lit-html",{createHTML:n=>n}):void 0,qt="$lit$",A=`lit$${Math.random().toFixed(9).slice(2)}$`,Vt="?"+A,be=`<${Vt}>`,H=document,J=()=>H.createComment(""),Q=n=>n===null||typeof n!="object"&&typeof n!="function",St=Array.isArray,ye=n=>St(n)||typeof n?.[Symbol.iterator]=="function",bt=`[ \t
\f\r]`,Y=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Gt=/-->/g,Ft=/>/g,R=RegExp(`>|${bt}(?:([^\\s"'>=/]+)(${bt}*=${bt}*(?:[^ \t
\f\r"'\`<>=]|("|')|))|$)`,"g"),Kt=/'/g,It=/"/g,Yt=/^(?:script|style|textarea|title)$/i,At=n=>(o,...t)=>({_$litType$:n,strings:o,values:t}),d=At(1),at=At(2),Ge=At(3),z=Symbol.for("lit-noChange"),l=Symbol.for("lit-nothing"),Wt=new WeakMap,B=H.createTreeWalker(H,129);function Jt(n,o){if(!St(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Ut!==void 0?Ut.createHTML(o):o}var $e=(n,o)=>{let t=n.length-1,e=[],i,s=o===2?"<svg>":o===3?"<math>":"",r=Y;for(let a=0;a<t;a++){let c=n[a],p,_,f=-1,b=0;for(;b<c.length&&(r.lastIndex=b,_=r.exec(c),_!==null);)b=r.lastIndex,r===Y?_[1]==="!--"?r=Gt:_[1]!==void 0?r=Ft:_[2]!==void 0?(Yt.test(_[2])&&(i=RegExp("</"+_[2],"g")),r=R):_[3]!==void 0&&(r=R):r===R?_[0]===">"?(r=i??Y,f=-1):_[1]===void 0?f=-2:(f=r.lastIndex-_[2].length,p=_[1],r=_[3]===void 0?R:_[3]==='"'?It:Kt):r===It||r===Kt?r=R:r===Gt||r===Ft?r=Y:(r=R,i=void 0);let g=r===R&&n[a+1].startsWith("/>")?" ":"";s+=r===Y?c+be:f>=0?(e.push(p),c.slice(0,f)+qt+c.slice(f)+A+g):c+A+(f===-2?a:g)}return[Jt(n,s+(n[t]||"<?>")+(o===2?"</svg>":o===3?"</math>":"")),e]},Z=class n{constructor({strings:o,_$litType$:t},e){let i;this.parts=[];let s=0,r=0,a=o.length-1,c=this.parts,[p,_]=$e(o,t);if(this.el=n.createElement(p,e),B.currentNode=this.el.content,t===2||t===3){let f=this.el.content.firstChild;f.replaceWith(...f.childNodes)}for(;(i=B.nextNode())!==null&&c.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let f of i.getAttributeNames())if(f.endsWith(qt)){let b=_[r++],g=i.getAttribute(f).split(A),u=/([.?@])?(.*)/.exec(b);c.push({type:1,index:s,name:u[2],strings:g,ctor:u[1]==="."?$t:u[1]==="?"?xt:u[1]==="@"?wt:D}),i.removeAttribute(f)}else f.startsWith(A)&&(c.push({type:6,index:s}),i.removeAttribute(f));if(Yt.test(i.tagName)){let f=i.textContent.split(A),b=f.length-1;if(b>0){i.textContent=rt?rt.emptyScript:"";for(let g=0;g<b;g++)i.append(f[g],J()),B.nextNode(),c.push({type:2,index:++s});i.append(f[b],J())}}}else if(i.nodeType===8)if(i.data===Vt)c.push({type:2,index:s});else{let f=-1;for(;(f=i.data.indexOf(A,f+1))!==-1;)c.push({type:7,index:s}),f+=A.length-1}s++}}static createElement(o,t){let e=H.createElement("template");return e.innerHTML=o,e}};function L(n,o,t=n,e){if(o===z)return o;let i=e!==void 0?t._$Co?.[e]:t._$Cl,s=Q(o)?void 0:o._$litDirective$;return i?.constructor!==s&&(i?._$AO?.(!1),s===void 0?i=void 0:(i=new s(n),i._$AT(n,t,e)),e!==void 0?(t._$Co??=[])[e]=i:t._$Cl=i),i!==void 0&&(o=L(n,i._$AS(n,o.values),i,e)),o}var yt=class{constructor(o,t){this._$AV=[],this._$AN=void 0,this._$AD=o,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(o){let{el:{content:t},parts:e}=this._$AD,i=(o?.creationScope??H).importNode(t,!0);B.currentNode=i;let s=B.nextNode(),r=0,a=0,c=e[0];for(;c!==void 0;){if(r===c.index){let p;c.type===2?p=new X(s,s.nextSibling,this,o):c.type===1?p=new c.ctor(s,c.name,c.strings,this,o):c.type===6&&(p=new kt(s,this,o)),this._$AV.push(p),c=e[++a]}r!==c?.index&&(s=B.nextNode(),r++)}return B.currentNode=H,i}p(o){let t=0;for(let e of this._$AV)e!==void 0&&(e.strings!==void 0?(e._$AI(o,e,t),t+=e.strings.length-2):e._$AI(o[t])),t++}},X=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(o,t,e,i){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=o,this._$AB=t,this._$AM=e,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let o=this._$AA.parentNode,t=this._$AM;return t!==void 0&&o?.nodeType===11&&(o=t.parentNode),o}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(o,t=this){o=L(this,o,t),Q(o)?o===l||o==null||o===""?(this._$AH!==l&&this._$AR(),this._$AH=l):o!==this._$AH&&o!==z&&this._(o):o._$litType$!==void 0?this.$(o):o.nodeType!==void 0?this.T(o):ye(o)?this.k(o):this._(o)}O(o){return this._$AA.parentNode.insertBefore(o,this._$AB)}T(o){this._$AH!==o&&(this._$AR(),this._$AH=this.O(o))}_(o){this._$AH!==l&&Q(this._$AH)?this._$AA.nextSibling.data=o:this.T(H.createTextNode(o)),this._$AH=o}$(o){let{values:t,_$litType$:e}=o,i=typeof e=="number"?this._$AC(o):(e.el===void 0&&(e.el=Z.createElement(Jt(e.h,e.h[0]),this.options)),e);if(this._$AH?._$AD===i)this._$AH.p(t);else{let s=new yt(i,this),r=s.u(this.options);s.p(t),this.T(r),this._$AH=s}}_$AC(o){let t=Wt.get(o.strings);return t===void 0&&Wt.set(o.strings,t=new Z(o)),t}k(o){St(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,e,i=0;for(let s of o)i===t.length?t.push(e=new n(this.O(J()),this.O(J()),this,this.options)):e=t[i],e._$AI(s),i++;i<t.length&&(this._$AR(e&&e._$AB.nextSibling,i),t.length=i)}_$AR(o=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);o!==this._$AB;){let e=Dt(o).nextSibling;Dt(o).remove(),o=e}}setConnected(o){this._$AM===void 0&&(this._$Cv=o,this._$AP?.(o))}},D=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(o,t,e,i,s){this.type=1,this._$AH=l,this._$AN=void 0,this.element=o,this.name=t,this._$AM=i,this.options=s,e.length>2||e[0]!==""||e[1]!==""?(this._$AH=Array(e.length-1).fill(new String),this.strings=e):this._$AH=l}_$AI(o,t=this,e,i){let s=this.strings,r=!1;if(s===void 0)o=L(this,o,t,0),r=!Q(o)||o!==this._$AH&&o!==z,r&&(this._$AH=o);else{let a=o,c,p;for(o=s[0],c=0;c<s.length-1;c++)p=L(this,a[e+c],t,c),p===z&&(p=this._$AH[c]),r||=!Q(p)||p!==this._$AH[c],p===l?o=l:o!==l&&(o+=(p??"")+s[c+1]),this._$AH[c]=p}r&&!i&&this.j(o)}j(o){o===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,o??"")}},$t=class extends D{constructor(){super(...arguments),this.type=3}j(o){this.element[this.name]=o===l?void 0:o}},xt=class extends D{constructor(){super(...arguments),this.type=4}j(o){this.element.toggleAttribute(this.name,!!o&&o!==l)}},wt=class extends D{constructor(o,t,e,i,s){super(o,t,e,i,s),this.type=5}_$AI(o,t=this){if((o=L(this,o,t,0)??l)===z)return;let e=this._$AH,i=o===l&&e!==l||o.capture!==e.capture||o.once!==e.once||o.passive!==e.passive,s=o!==l&&(e===l||i);i&&this.element.removeEventListener(this.name,this,e),s&&this.element.addEventListener(this.name,this,o),this._$AH=o}handleEvent(o){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,o):this._$AH.handleEvent(o)}},kt=class{constructor(o,t,e){this.element=o,this.type=6,this._$AN=void 0,this._$AM=t,this.options=e}get _$AU(){return this._$AM._$AU}_$AI(o){L(this,o)}};var xe=Et.litHtmlPolyfillSupport;xe?.(Z,X),(Et.litHtmlVersions??=[]).push("3.3.3");var Qt=(n,o,t)=>{let e=t?.renderBefore??o,i=e._$litPart$;if(i===void 0){let s=t?.renderBefore??null;e._$litPart$=i=new X(o.insertBefore(J(),s),s,void 0,t??{})}return i._$AI(n),i};var Ct=globalThis,w=class extends S{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let o=super.createRenderRoot();return this.renderOptions.renderBefore??=o.firstChild,o}update(o){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(o),this._$Do=Qt(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return z}};w._$litElement$=!0,w.finalized=!0,Ct.litElementHydrateSupport?.({LitElement:w});var we=Ct.litElementPolyfillSupport;we?.({LitElement:w});(Ct.litElementVersions??=[]).push("4.2.2");var ke={attribute:!0,type:String,converter:V,reflect:!1,hasChanged:nt},Ee=(n=ke,o,t)=>{let{kind:e,metadata:i}=t,s=globalThis.litPropertyMetadata.get(i);if(s===void 0&&globalThis.litPropertyMetadata.set(i,s=new Map),e==="setter"&&((n=Object.create(n)).wrapped=!0),s.set(t.name,n),e==="accessor"){let{name:r}=t;return{set(a){let c=o.get.call(this);o.set.call(this,a),this.requestUpdate(r,c,n,!0,a)},init(a){return a!==void 0&&this.C(r,void 0,n,a),a}}}if(e==="setter"){let{name:r}=t;return function(a){let c=this[r];o.call(this,a),this.requestUpdate(r,c,n,!0,a)}}throw Error("Unsupported decorator location: "+e)};function U(n){return(o,t)=>typeof t=="object"?Ee(n,o,t):((e,i,s)=>{let r=i.hasOwnProperty(s);return i.constructor.createProperty(s,e),r?Object.getOwnPropertyDescriptor(i,s):void 0})(n,o,t)}function C(n){return U({...n,state:!0,attribute:!1})}var O=n=>Math.max(0,Math.min(75,n));function Pt(n,o="theme"){let t=O(n.upper.angle??0),e=O(n.lower.angle??0),i=`rotate(${t} 150 70)`,s=`rotate(${-e} 150 70)`,r=a=>a.angle===void 0?"":`${a.label?`${a.label} `:""}${Math.round(O(a.angle))}\xB0`;return at`
    <svg
      class="bed-graphic bed-graphic-${o} ${n.moving?"is-moving":""}"
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
        <g class="bed-panel" transform=${s}>
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
  `}function Tt(n){let o=O(n.left.upper.angle??0),t=O(n.left.lower.angle??0),e=O(n.right.upper.angle??0),i=O(n.right.lower.angle??0),s=(r,a,c,p)=>at`
    <g
      class="dual-bed-side dual-bed-side-${r} ${p?"is-moving":""}"
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
  `;return at`
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
      ${s("right",e,i,n.right.moving)}
      ${s("left",o,t,n.left.moving)}
    </svg>
  `}function Mt(n){let o=n.find(e=>e.key==="back"||e.key==="head"),t=n.find(e=>e.key==="legs"||e.key==="feet");return o&&t?{upper:o,lower:t}:void 0}function Zt(n,o){let t=n.motors.filter(e=>{let i=e.angle??e.position;return o.states[i??""]?.attributes.unit_of_measurement==="\xB0"});return Mt(t)!==void 0}var lt=class{constructor(o){this.actions=o;this._key=null;this._cover=null;this._stop=null;this._pointerId=null;this._generation=0}get heldKey(){return this._key}start(o,t,e,i){this._key===null&&(this._key=o.key,this._cover=o.cover??null,this._stop=i??null,this._pointerId=e,this._repeat(o,t,++this._generation))}async _repeat(o,t,e){for(;e===this._generation;)try{let i=this.actions.pulse(o,t);if(!i)return;await i}catch{return}}endFromPointer(o,t,e){this._pointerId!==null&&t!==this._pointerId||e&&this.end(o)}end(o){let t=this._stop??void 0;if(this.cancel(o)){if(o.cover){this.actions.stopCover(o.cover);return}this.actions.stopBed(t)}}cancel(o){return!o||this._key!==o.key?!1:(this._reset(),!0)}stopAll(o){let t=o??this._stop??void 0;this._reset(),this.actions.stopBed(t)}abandon(){let o=this._cover,t=this._stop??void 0,e=this._key!==null;this._reset(),e&&(o?this.actions.stopCover(o):this.actions.stopBed(t))}_reset(){this._key=null,this._cover=null,this._stop=null,this._pointerId=null,this._generation++}};var Xt={"section.position":"Position","section.firmness":"Firmness","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","section.massage":"Massage","section.utility":"Utility","section.climate":"Climate","section.connection":"Connection","section.bluetooth":"Bluetooth","action.up":"Up","action.stop":"Stop","action.stop_all":"Stop all","action.down":"Down","motor.back":"Back","motor.legs":"Legs","motor.head":"Head","motor.feet":"Feet","motor.lumbar":"Lumbar","motor.pillow":"Pillow","motor.neck":"Neck","motor.tilt":"Tilt","motor.hip":"Hip","motor.bed_height":"Bed height","motor.stair":"Stair","status.connected":"Connected","status.connecting":"Connecting","status.idle":"Idle \u2014 reconnects on demand","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_firmness":"Firmness","editor.show_presets":"Presets","editor.move_up":"Move up","editor.move_down":"Move down","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls","card.both_sides":"Both sides","card.left_side":"Left","card.right_side":"Right","combined.lights":"Both under-bed lights","combined.on":"On","combined.off":"Off","combined.mixed":"One side on","sync.label":"Match both to","sync.incomplete":"Some positions could not be synchronized.","compact.open":"Open full bed view","compact.target":"Actions","compact.target_missing":"Choose an available action target in the card settings.","compact.no_position":"Position feedback unavailable","editor.layout":"Layout","editor.layout_full":"Full card","editor.layout_compact":"Compact card","editor.recipe_hint":"Apply a compact starting point, then customize the options below.","editor.recipe_glance":"A \xB7 Glance only","editor.recipe_quick":"B \xB7 Quick actions","editor.recipe_controls":"C \xB7 Compact controls","editor.compact_appearance":"Compact appearance","editor.compact_controls":"Compact controls","editor.compact_actions":"Quick actions and order","editor.compact_actions_hint":"Choose presets or memory recalls. Only actions supported by the selected side appear. Stop is added automatically.","editor.compact_stop_hint":"Stop remains available with movement controls and stops movement started by this card, including after changing sides.","editor.actions_auto":"Automatic favourites","editor.compact_labels":"Side readouts","editor.labels_angles":"Names and positions","editor.labels_names":"Names only","editor.labels_none":"None","editor.show_header":"Title","editor.show_side_selector":"Side selector","editor.default_target":"Default / fixed target","editor.animate":"Animate position changes","editor.navigation_path":"Full view path (optional)","editor.show_utility":"Utility","editor.compact_connection":"Connection status"};var te={"section.position":"Posisjon","section.firmness":"Fasthet","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","section.massage":"Massasje","section.utility":"Verkt\xF8y","section.climate":"Klima","section.connection":"Tilkobling","section.bluetooth":"Bluetooth","action.up":"Opp","action.stop":"Stopp","action.stop_all":"Stopp alt","action.down":"Ned","motor.back":"Rygg","motor.legs":"Ben","motor.head":"Hode","motor.feet":"F\xF8tter","motor.lumbar":"Korsrygg","motor.pillow":"Pute","motor.neck":"Nakke","motor.tilt":"Vipp","motor.hip":"Hofte","motor.bed_height":"Sengeh\xF8yde","motor.stair":"Trinn","status.connected":"Tilkoblet","status.connecting":"Kobler til","status.idle":"Hvilemodus \u2013 kobler til ved behov","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_firmness":"Fasthet","editor.show_presets":"Forh\xE5ndsvalg","editor.move_up":"Flytt opp","editor.move_down":"Flytt ned","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller","card.both_sides":"Begge sider","card.left_side":"Venstre","card.right_side":"H\xF8yre","combined.lights":"Begge sengelys","combined.on":"P\xE5","combined.off":"Av","combined.mixed":"\xC9n side p\xE5","sync.label":"Synkroniser begge til","sync.incomplete":"Noen posisjoner kunne ikke synkroniseres.","compact.open":"\xC5pne full sengevisning","compact.target":"Handlinger","compact.target_missing":"Velg et tilgjengelig m\xE5l for handlinger i kortinnstillingene.","compact.no_position":"Posisjonsdata er utilgjengelige","editor.layout":"Utforming","editor.layout_full":"Fullt kort","editor.layout_compact":"Kompakt kort","editor.recipe_hint":"Velg et kompakt utgangspunkt, og tilpass valgene nedenfor.","editor.recipe_glance":"A \xB7 Kun oversikt","editor.recipe_quick":"B \xB7 Hurtighandlinger","editor.recipe_controls":"C \xB7 Kompakte kontroller","editor.compact_appearance":"Kompakt utseende","editor.compact_controls":"Kompakte kontroller","editor.compact_actions":"Hurtighandlinger og rekkef\xF8lge","editor.compact_actions_hint":"Velg forh\xE5ndsinnstillinger eller minneposisjoner. Bare handlinger for den valgte siden vises. Stopp legges til automatisk.","editor.compact_stop_hint":"Stopp vises sammen med bevegelseskontroller og stopper bevegelser startet fra dette kortet, ogs\xE5 etter sidebytte.","editor.actions_auto":"Automatiske favoritter","editor.compact_labels":"Sideinformasjon","editor.labels_angles":"Navn og posisjoner","editor.labels_names":"Bare navn","editor.labels_none":"Ingen","editor.show_header":"Tittel","editor.show_side_selector":"Sidevelger","editor.default_target":"Standard / fast m\xE5l","editor.animate":"Animer posisjonsendringer","editor.navigation_path":"Sti til full visning (valgfritt)","editor.show_utility":"Verkt\xF8y","editor.compact_connection":"Tilkoblingsstatus"};var j={en:Xt,nb:te};function Ce(n){let o=(n?.locale?.language||n?.language||"en").toLowerCase(),t=o.split("-")[0];return j[o]?j[o]:j[t]?j[t]:t==="nn"||t==="no"?j.nb:j.en}function h(n,o,t){let i=Ce(n)[o]??j.en[o]??o;if(t)for(let[s,r]of Object.entries(t))i=i.replace(`{${s}}`,r);return i}var ee=["glance","quick","controls"];function ie(n,o){let t={...n,layout:"compact",show_header:!0,show_graphic:!0,compact_labels:o==="glance"?"names":"angles",show_side_selector:!0,show_motors:o==="controls",show_lighting:!1,show_connection:!1,animate:!0};return o==="glance"?t.compact_actions=[]:delete t.compact_actions,t}function Rt(n,o){return[...o.presets,...o.memory.flatMap(t=>t.goto?[t.goto]:[])].flatMap(t=>{let e=n.entities[t]?.translation_key;return e?[{key:F(e).key,entityId:t}]:[]})}function dt(n,o,t){let e=Rt(n,o);if(t){let r=new Map(e.map(a=>[a.key,a]));return[...new Set(t)].flatMap(a=>{let c=r.get(a);return c?[c]:[]})}let i=e.find(r=>r.key==="preset_flat"),s=e.find(r=>r.key.startsWith("preset_memory_"))??e.find(r=>r!==i);return[i,s].filter(r=>r!==void 0)}function pt(n){return n.stop?[n.stop]:n.motors.flatMap(o=>o.cover?[o.cover]:[])}function ht(n){if(!(!n||!n.startsWith("/")||/^\/[/\\]/.test(n)||/[\\\s]/.test(n)))return n}function ut(n,o){let t=et(n,o),e=K(n,t);return t&&e.length?[{key:"both",label:h(n,"card.both_sides"),bed:y(n,t)},...e.map(i=>({key:i,label:n.devices[i]?.name_by_user??n.devices[i]?.name??i,bed:y(n,i)}))]:tt(n,o)?["both","left","right"].map(i=>({key:i,label:h(n,`card.${i==="both"?"both_sides":`${i}_side`}`),bed:y(n,o,i)})):[{key:"both",label:h(n,"card.both_sides"),bed:y(n,o)}]}var oe="4.0.0";function se(n,o){return{graphic:Zt(n,o),motors:n.motors.some(t=>t.cover||t.up||t.down)||!!n.stop||!!n.synchro,firmness:n.firmness.length>0,presets:n.presets.length>0,memory:n.memory.length>0,lighting:!!(n.lights.light||n.lights.switch||n.lights.level||n.lights.toggle||n.lights.cycle||n.lights.timer),massage:n.massage.buttons.length>0||n.massage.numbers.length>0||!!n.massage.timer,utility:n.utility.length>0,climate:n.climate.entities.length>0||n.climate.selects.length>0,connection:!!(n.connect||n.disconnect)}}var Pe="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",Te="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z",Me=(n,o)=>n.length===o.length&&n.every((t,e)=>t===o[e]),G=class extends w{constructor(){super(...arguments);this._computeLabel=t=>h(this.hass,`editor.${t.name}`)}setConfig(t){this._config=t}_bed(){let t=this._config?.device_id;if(!this.hass||!t)return;let e=ut(this.hass,t).map(r=>r.bed),i=e[0];if(!i)return;let s=new Map;for(let r of e)for(let a of r.memory){let c=s.get(a.slot);s.set(a.slot,{slot:a.slot,goto:c?.goto??a.goto,save:c?.save??a.save})}return{...i,memory:[...s.values()].sort((r,a)=>r.slot-a.slot)}}_presentKeys(t){let e=this.hass?ut(this.hass,this._config?.device_id).map(i=>i.bed):[t];return N.filter(i=>e.some(s=>se(s,this.hass)[i]))}_orderedKeys(t){let e=this._presentKeys(t),s=(this._config?.section_order??[]).filter(a=>e.includes(a)),r=e.filter(a=>!s.includes(a));return[...s,...r]}_memorySlots(t){return t?t.memory.map(e=>e.slot):[]}_slotLabel(t){let e=t.goto??t.save,i=e&&this.hass?.states[e]?.attributes.friendly_name||`Memory ${t.slot}`,s=e&&this.hass?.entities[e]?.device_id,r=s?this.hass?.devices[s]:void 0,a=r?.name_by_user||r?.name;return a&&i.startsWith(`${a} `)?i.slice(a.length+1):i}_emit(t){t.type=t.type??"custom:adjustable-bed-card",t.name||delete t.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(t){t.stopPropagation();let e=t.detail.value,i=this._cfg;i.device_id!==e.device_id&&delete i.default_target,i.device_id=e.device_id||void 0,e.name?i.name=e.name:delete i.name,this._emit(i)}_toggleSection(t,e){let i=this._cfg;e?delete i[`show_${t}`]:i[`show_${t}`]=!1,this._emit(i)}_moveSection(t,e,i){let s=this._orderedKeys(t),r=s.indexOf(e),a=r+i;if(r<0||a<0||a>=s.length)return;[s[r],s[a]]=[s[a],s[r]];let c=this._cfg;Me(s,this._presentKeys(t))?delete c.section_order:c.section_order=s,this._emit(c)}_setMemorySave(t){let e=this._cfg;t?delete e.memory_save:e.memory_save=!1,this._emit(e)}_slotChecked(t){let e=this._config?.memory_slots;return!e||!e.length||e.map(Number).includes(t)}_toggleSlot(t,e,i){let s=this._memorySlots(t),r=this._config?.memory_slots,a=r&&r.length?r.map(Number):[...s];i?a.includes(e)||a.push(e):a=a.filter(p=>p!==e),a.sort((p,_)=>p-_);let c=this._cfg;a.length===s.length?delete c.memory_slots:c.memory_slots=a,this._emit(c)}_sectionsGroup(t){let e=this._orderedKeys(t);return e.length?d`
      <div class="group">
        <div class="group-title">${h(this.hass,"editor.sections")}</div>
        ${e.map((i,s)=>{let r=this._config?.[`show_${i}`]!==!1;return d`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${s===0}
                  @click=${()=>this._moveSection(t,i,-1)}
                  title=${h(this.hass,"editor.move_up")}
                  aria-label=${h(this.hass,"editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Pe}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${s===e.length-1}
                  @click=${()=>this._moveSection(t,i,1)}
                  title=${h(this.hass,"editor.move_down")}
                  aria-label=${h(this.hass,"editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${Te}></path></svg>
                </button>
              </div>
              <span class="label">${h(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${r}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:l}_memoryGroup(t){if(!(t.memory.length>0&&this._config?.show_memory!==!1))return l;let i=t.memory.some(r=>r.save),s=t.memory.length>1;return!i&&!s?l:d`
      <div class="group">
        <div class="group-title">
          ${h(this.hass,"editor.memory_group")}
        </div>
        ${i?d`<div class="row">
                <span class="label">${h(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${r=>this._setMemorySave(r.target.checked)}
                ></ha-switch>
              </div>`:l}
        ${s?d`<div class="sub">
                <div class="sub-label">
                  ${h(this.hass,"editor.memory_slots")}
                </div>
                ${t.memory.map(r=>d`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(r.slot)}
                        @change=${a=>this._toggleSlot(t,r.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(r)}</span>
                    </label>
                  `)}
              </div>`:l}
      </div>
    `}_setOption(t,e){this._emit({...this._cfg,[t]:e})}_compactToggle(t,e){return d`<div class="row"><span class="label">${h(this.hass,t==="show_connection"?"editor.compact_connection":`editor.${t}`)}</span>
      <ha-switch .checked=${this._config?.[t]??e}
        @change=${i=>this._setOption(t,i.target.checked)}></ha-switch>
    </div>`}_compactGroup(){let t=this._config,e=ut(this.hass,t.device_id),i=e.find(c=>c.key===(t.default_target??"both")),s=e.flatMap(c=>Rt(this.hass,c.bed)).filter((c,p,_)=>_.findIndex(f=>f.key===c.key)===p),r=t.compact_actions??(i?dt(this.hass,i.bed).map(c=>c.key):[]),a=[...r.filter(c=>s.some(p=>p.key===c)),...s.map(c=>c.key).filter(c=>!r.includes(c))];return d`
      <div class="group">
        <div class="group-title">${h(this.hass,"editor.compact_appearance")}</div>
        ${this._compactToggle("show_header",!0)}
        ${this._compactToggle("show_graphic",!0)}
        <label class="row"><span class="label">${h(this.hass,"editor.compact_labels")}</span>
          <select .value=${t.compact_labels??"angles"}
            @change=${c=>this._setOption("compact_labels",c.target.value)}>
            ${["angles","names","none"].map(c=>d`
              <option value=${c}>${h(this.hass,`editor.labels_${c}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate",!0)}
        <label class="row path-row"><span class="label">${h(this.hass,"editor.navigation_path")}</span>
          <input type="text" .value=${t.navigation_path??""} placeholder="/dashboard/bed"
            @change=${c=>this._setOption("navigation_path",c.target.value||void 0)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${h(this.hass,"editor.compact_controls")}</div>
        ${e.length>1||!i?d`
          ${this._compactToggle("show_side_selector",!0)}
          <label class="row"><span class="label">${h(this.hass,"editor.default_target")}</span>
            <select .value=${t.default_target??"both"}
              @change=${c=>this._setOption("default_target",c.target.value)}>
              ${i?l:d`<option value=${t.default_target}>${h(this.hass,"compact.target_missing")}</option>`}
              ${e.map(c=>d`<option value=${c.key}>${c.label}</option>`)}
            </select>
          </label>`:l}
        ${this._compactToggle("show_motors",!1)}
        ${this._compactToggle("show_lighting",!1)}
        ${this._compactToggle("show_connection",!1)}
        <p class="hint">${h(this.hass,"editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${h(this.hass,"editor.compact_actions")}</div>
        <p class="hint">${h(this.hass,"editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${()=>this._setOption("compact_actions",void 0)}>${h(this.hass,"editor.actions_auto")}</button>
          <button @click=${()=>this._setOption("compact_actions",[])}>${h(this.hass,"editor.labels_none")}</button>
        </div>
        ${a.map(c=>{let p=s.find(u=>u.key===c),_=r.includes(c),f=r.indexOf(c),b=u=>{let $=[...r];[$[f],$[f+u]]=[$[f+u],$[f]],this._setOption("compact_actions",$)},g=this.hass.states[p.entityId];return d`<div class="row">
            <ha-checkbox .checked=${_} @change=${u=>this._setOption("compact_actions",u.target.checked?[...r,c]:r.filter($=>$!==c))}></ha-checkbox>
            <span class="label">${g?.attributes.friendly_name??c}</span>
            <button class="icon-btn" ?disabled=${!_||f===0}
              aria-label=${h(this.hass,"editor.move_up")} @click=${()=>b(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!_||f===r.length-1}
              aria-label=${h(this.hass,"editor.move_down")} @click=${()=>b(1)}>↓</button>
          </div>`})}
      </div>`}_layoutGroup(){return d`<div class="group">
      <label class="row"><span class="label">${h(this.hass,"editor.layout")}</span>
        <select .value=${this._config?.layout??"full"}
          @change=${t=>this._setOption("layout",t.target.value)}>
          <option value="full">${h(this.hass,"editor.layout_full")}</option>
          <option value="compact">${h(this.hass,"editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${h(this.hass,"editor.recipe_hint")}</p>
      <div class="recipes">${ee.map(t=>d`
        <button @click=${()=>this._emit({...ie(this._config,t)})}>
          ${h(this.hass,`editor.recipe_${t}`)}
        </button>`)}</div>
    </div>`}render(){if(!this.hass||!this._config)return l;let t=this._bed();return d`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout==="compact"?this._compactGroup():d`
        ${t?this._sectionsGroup(t):l}
        ${t?this._memoryGroup(t):l}
      `}
    `}};G.styles=W`
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
  `,x([U({attribute:!1})],G.prototype,"hass",2),x([C()],G.prototype,"_config",2);customElements.get("adjustable-bed-card-editor")||customElements.define("adjustable-bed-card-editor",G);var Re=new Set(["back","legs","head","feet"]),k=class extends w{constructor(){super(...arguments);this._activePairedPane="both";this._synchronizationFailed=!1;this._watched=[];this._compactStopTargets=new Set;this._hold=new lt({pulse:(t,e)=>{if(t.cover)return this.hass?.callService("cover",e==="up"?"open_cover":"close_cover",{entity_id:t.cover});let i=e==="up"?t.up:t.down;return i?this.hass?.callService("button","press",{entity_id:i}):void 0},stopCover:t=>this._cover(t,"stop_cover"),stopBed:t=>{t&&this._press(t)}});this._navigate=()=>{let t=ht(this._config?.navigation_path);t&&(this._hold.abandon(),history.pushState(null,"",t),window.dispatchEvent(new CustomEvent("location-changed",{detail:{replace:!1}})))}}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(t){return{type:"custom:adjustable-bed-card",device_id:t?Object.values(t.entities).find(i=>i.platform===T)?.device_id:void 0}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._config&&(this._hold.abandon(),this._stopCompact()),(t.device_id!==this._config?.device_id||t.default_target!==this._config?.default_target)&&(this._activePairedPane=t.default_target??"both"),this._config=t}getCardSize(){if(this._config?.layout!=="compact")return 8;let t=this._config;return Math.ceil((24+(t.show_header!==!1?36:0)+(t.show_graphic!==!1?150:0)+(t.compact_labels!=="none"?40:0)+(t.compact_actions?.length===0?0:110)+(t.show_motors===!0?180:0)+(t.show_lighting===!0?70:0)+(t.show_connection===!0?50:0))/50)}getGridOptions(){return{columns:this._config?.layout==="compact"?6:12,min_columns:6,rows:"auto"}}disconnectedCallback(){super.disconnectedCallback(),this._hold.abandon()}shouldUpdate(t){if(t.has("_config")||t.has("_saveModeFor")||t.has("_activePairedPane")||t.has("_synchronizingTo")||t.has("_synchronizationFailed")||!t.has("hass")||!this.hass)return!0;let e=t.get("hass");if(!e||e.entities!==this.hass.entities||e.devices!==this.hass.devices)return!0;for(let i of this._watched)if(e.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return l;if(!this._config.device_id)return this._notice("card.no_device");let t=et(this.hass,this._config.device_id),e=K(this.hass,t);if(t&&e.length)return this._renderPaired(t,e);if(this._config.device_id&&tt(this.hass,this._config.device_id))return this._renderSingleAddressPaired(this._config.device_id);let i=y(this.hass,this._config.device_id);return this._watched=this._collectWatched(i),M(i)?this._notice("card.no_entities"):this._config.layout==="compact"?this._renderCompact(this._config.device_id,[{key:"both",label:this._title(),icon:"mdi:bed-outline",bed:i}],!1):d`
      <ha-card>
        ${this._header(i)}
        ${this._renderSections(i)}
      </ha-card>
    `}_renderSections(t,e="theme",i){let s=this._config,r={graphic:()=>s.show_graphic!==!1?i??this._graphic(t,e):l,motors:()=>s.show_motors!==!1?this._motors(t):l,firmness:()=>s.show_firmness!==!1?this._firmness(t):l,presets:()=>s.show_presets!==!1?this._presets(t):l,memory:()=>s.show_memory!==!1?this._memory(t):l,lighting:()=>s.show_lighting!==!1?this._lighting(t):l,massage:()=>s.show_massage!==!1?this._massage(t):l,utility:()=>s.show_utility!==!1?this._utility(t):l,climate:()=>s.show_climate!==!1?this._climate(t):l,connection:()=>s.show_connection!==!1?this._connection(t):l};return this._orderedSections().map(a=>r[a]?.()??l)}_renderPaired(t,e){let i=this.hass,s=y(i,t),r=e.map((a,c)=>({key:a,label:this._deviceLabel(a),icon:"mdi:bed-single-outline",bed:y(i,a),graphicTone:c===0?"left":"right",synchronizationTarget:{deviceId:a}}));return this._watched=[s,...r.map(a=>a.bed)].flatMap(a=>this._collectWatched(a)),M(s)&&r.every(a=>M(a.bed))?this._notice("card.no_entities"):this._renderPairedCard(t,[{key:"both",label:h(i,"card.both_sides"),icon:"mdi:link-variant",bed:s},...r])}_renderSingleAddressPaired(t){let e=this.hass,i={both:y(e,t,"both"),left:y(e,t,"left"),right:y(e,t,"right")};return this._watched=Object.values(i).flatMap(s=>this._collectWatched(s)),Object.values(i).every(s=>M(s))?this._notice("card.no_entities"):this._renderPairedCard(t,[{key:"both",label:h(e,"card.both_sides"),icon:"mdi:link-variant",bed:i.both},{key:"left",label:h(e,"card.left_side"),icon:"mdi:bed-single-outline",bed:i.left,graphicTone:"left",synchronizationTarget:{deviceId:t,side:"left"}},{key:"right",label:h(e,"card.right_side"),icon:"mdi:bed-single-outline",bed:i.right,graphicTone:"right",synchronizationTarget:{deviceId:t,side:"right"}}])}_renderPairedCard(t,e){if(this._config?.layout==="compact")return this._renderCompact(t,e,!0);let i=e.filter(c=>!M(c.bed)),s=i.find(c=>c.key===this._activePairedPane)??i[0],r=i.filter(c=>c.key!=="both"),a=s.key==="both";return d`
      <ha-card class="paired-card">
        ${this._header(s.bed,t)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${i.length}`}
        >
          ${i.map(c=>d`
              <button
                class="pane-tab ${c.key===s.key?"active":""}"
                role="tab"
                aria-selected=${c.key===s.key?"true":"false"}
                @click=${()=>this._selectPairedPane(c.key)}
              >
                <ha-icon icon=${c.icon}></ha-icon>
                <span>${c.label}</span>
                ${this._connectionDot(c.bed)}
              </button>
            `)}
        </div>
        <div class="pane" role="tabpanel" aria-label=${s.label}>
          ${this._renderSections(s.bed,s.graphicTone,a?this._pairedOverview(r):void 0)}
          ${a&&this._config?.show_lighting!==!1?this._combinedLighting(s.bed,r):l}
          ${a&&this._config?.show_connection!==!1?this._combinedBluetooth(r):l}
        </div>
      </ha-card>
    `}_renderCompact(t,e,i){let s=this._config,r=e.find(v=>v.key===this._activePairedPane),a=r?.bed,c=a?dt(this.hass,a,s.compact_actions):[],p=s.show_motors===!0&&a?a.motors.filter(v=>v.cover||v.up||v.down||v.position):[],_=c.length>0||p.length>0||s.show_lighting===!0,f=s.compact_actions?.length!==0||s.show_motors===!0||s.show_lighting===!0,b=i?e.filter(v=>v.key!=="both"):e,g=!!a&&pt(a).length>0,u=c.length>0||p.length>0,$=ht(s.navigation_path);return d`
      <ha-card class="compact-card ${f?"":"compact-glance"} ${s.animate===!1?"no-animation":""}">
        ${s.show_header!==!1?d`
          <div class="compact-header">
            <span class="title">${this._title(t)}</span>
            ${$?d`<button class="compact-open" @click=${this._navigate}
              aria-label=${h(this.hass,"compact.open")}>
              <ha-icon icon="mdi:open-in-new"></ha-icon>
            </button>`:l}
          </div>`:l}
        ${i&&f?s.show_side_selector!==!1?d`
          <div class="pane-tabs compact-tabs" role="group"
            aria-label=${h(this.hass,"compact.target")}>
            ${e.filter(v=>!M(v.bed)).map(v=>d`
              <button class="pane-tab ${v.key===r?.key?"active":""}"
                aria-pressed=${v.key===r?.key?"true":"false"}
                title=${v.label}
                @click=${()=>this._selectPairedPane(v.key)}>
                <span>${v.label}</span>
              </button>`)}
          </div>`:d`<div class="compact-target">
            ${h(this.hass,"compact.target")}: ${r?.label??h(this.hass,"compact.target_missing")}
          </div>`:l}
        ${s.show_graphic!==!1?this._compactGraphic(b):l}
        ${this._compactReadouts(b)}
        ${!r&&f?d`<div class="hint" role="status">
          ${h(this.hass,"compact.target_missing")}</div>`:l}
        ${p.length?d`<div class="rows compact-motors">
          ${p.map(v=>v.cover||v.up||v.down?this._motorRow(v,a?.stop):this._moreInfoRow(v.position))}
        </div>`:l}
        ${c.length||u||this._compactStopTargets.size?d`
          <div class="tiles compact-actions">
            ${c.map(({entityId:v})=>d`<button class="tile"
              ?disabled=${!g||!this._available(v)}
              @click=${()=>this._compactRecall(v,a)}>
              ${this._icon(v)}<span class="tile-label">${this._name(v)}</span>
            </button>`)}
            <button class="tile compact-stop"
              ?disabled=${!g&&this._compactStopTargets.size===0}
              @click=${()=>this._stopCompact(a)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span class="tile-label">${h(this.hass,"action.stop")}</span>
            </button>
          </div>`:l}
        ${s.show_lighting===!0&&a?d`
          ${this._lighting(a)}
          ${i&&r?.key==="both"?this._combinedLighting(a,b):l}
        `:l}
        ${s.show_connection===!0?d`<div class="compact-connections">
          ${b.map(v=>{let E=this._connectionStatus(v.bed);return E?d`<span>${this._connectionDot(v.bed)}
              ${v.label}: ${h(this.hass,`status.${E}`)}</span>`:l})}
        </div>`:l}
        ${!_&&s.show_graphic===!1&&s.compact_labels==="none"&&s.show_header===!1&&s.show_connection!==!0?d`<div class="hint">${this._title(t)}</div>`:l}
      </ha-card>`}_compactGraphic(t){let e=t.map(p=>this._graphicState(p.bed)),i=e[0],s=e[1],r=e.length>0&&e.every(p=>p!==void 0),a=t.map((p,_)=>`${p.label}: ${e[_]?this._positionSummary(e[_]):h(this.hass,"compact.no_position")}`).join(". "),c=r&&i?s?Tt({left:i,right:s}):Pt({...i,upper:{angle:i.upper.angle},lower:{angle:i.lower.angle}}):d`<div class="compact-no-position"><ha-icon icon="mdi:bed-outline"></ha-icon>
          <span>${h(this.hass,"compact.no_position")}</span></div>`;return ht(this._config?.navigation_path)?d`<button class="compact-graphic" @click=${this._navigate}
          aria-label="${h(this.hass,"compact.open")}. ${a}">${c}</button>`:d`<div class="compact-graphic" role="img" aria-label=${a}>${c}</div>`}_compactReadouts(t){let e=this._config?.compact_labels??"angles";return e==="none"?l:d`<div class="compact-readouts">
      ${t.map(i=>d`<div class="side-${i.graphicTone??"theme"}">
        <span class="compact-side-name"><span class="dual-swatch"></span>${i.label}</span>
        ${e==="angles"?d`<span class="compact-position">${i.bed.motors.filter(s=>s.angle||s.position||s.cover).map(s=>`${this._motorName(s)} ${this._readout(s)??"?"}`).join(" \xB7 ")||h(this.hass,"compact.no_position")}</span>`:l}
      </div>`)}
    </div>`}_available(t){let e=this._state(t)?.state;return e!==void 0&&e!=="unavailable"}_compactRecall(t,e){this._hold.abandon(),pt(e).forEach(i=>this._compactStopTargets.add(i)),this._press(t),this.requestUpdate()}_stopCompact(t){this._hold.abandon();let e=new Set([...this._compactStopTargets,...t?pt(t):[]]);this._compactStopTargets.clear();for(let i of e)i.startsWith("cover.")?this._cover(i,"stop_cover"):this._press(i);e.size&&this.requestUpdate()}_selectPairedPane(t){this._activePairedPane!==t&&(this._hold.abandon(),this._activePairedPane=t,this._saveModeFor=void 0,this._synchronizationFailed=!1)}_connectionStatus(t){if(!t.connectivity)return;let e=this._state(t.connectivity);return e?.attributes?.state_detail==="connecting"?"connecting":e?.state==="on"?"connected":e?.attributes?.state_detail==="idle"?"idle":"disconnected"}_connectionDot(t){let e=this._connectionStatus(t);return e?d`<span
      class="connection-dot ${e}"
      title=${h(this.hass,`status.${e}`)}
    ></span>`:l}_pairedOverview(t){let e=t.map(r=>({pane:r,graphic:this._graphicState(r.bed)})).filter(r=>r.graphic!==void 0);if(e.length<2)return l;let[i,s]=e;return d`
      <div class="graphic dual-graphic">
        ${Tt({left:i.graphic,right:s.graphic})}
      </div>
      <div class="dual-readouts">
        ${[i,s].map(({pane:r,graphic:a},c)=>d`
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
      ${this._synchronizeSelector(i.pane,s.pane)}
    `}_synchronizeSelector(t,e){if(!t.synchronizationTarget||!e.synchronizationTarget)return l;let i=this._synchronizationPlan(t.bed,e.bed),s=this._synchronizationPlan(e.bed,t.bed);if(i.length===0&&s.length===0)return l;let r=this._synchronizingTo!==void 0;return d`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${h(this.hass,"sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${this._synchronizingTo==="left"?"is-active":""}"
            aria-label="${h(this.hass,"sync.label")} ${t.label}"
            aria-busy=${this._synchronizingTo==="left"?"true":"false"}
            ?disabled=${r||i.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"left")}
          >
            ${this._synchronizingTo==="left"?d`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:d`<span class="dual-swatch"></span>`}
            <span>${t.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${this._synchronizingTo==="right"?"is-active":""}"
            aria-label="${h(this.hass,"sync.label")} ${e.label}"
            aria-busy=${this._synchronizingTo==="right"?"true":"false"}
            ?disabled=${r||s.length===0}
            @click=${()=>void this._synchronizePositions(t,e,"right")}
          >
            ${this._synchronizingTo==="right"?d`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`:d`<span class="dual-swatch"></span>`}
            <span>${e.label}</span>
          </button>
        </div>
      </div>
      ${this._synchronizationFailed?d`<div class="dual-sync-error" role="status">
            <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
            <span>${h(this.hass,"sync.incomplete")}</span>
          </div>`:l}
    `}_synchronizationPlan(t,e){let i=new Map(e.motors.map(a=>[a.key,a])),s=t.motors.filter(a=>Re.has(a.key)&&i.has(a.key)&&this._hasPositionFeedback(a)&&this._hasPositionFeedback(i.get(a.key)));if(s.length===0)return[];let r=s.map(a=>({motor:a.key,position:this._angle(a)}));return r.some(a=>a.position===void 0)||s.some(a=>this._angle(i.get(a.key))===void 0)?[]:r}_hasPositionFeedback(t){return t.angle!==void 0||t.position!==void 0}async _synchronizePositions(t,e,i){if(this._synchronizingTo||!this.hass)return;let s=i==="left"?t:e,r=i==="left"?e:t,a=r.synchronizationTarget;if(!a)return;let c=this._synchronizationPlan(s.bed,r.bed);if(c.length!==0){this._synchronizingTo=i,this._synchronizationFailed=!1;try{await this.hass.callService(T,"set_positions",{device_id:[a.deviceId],positions:c,...a.side?{side:a.side}:{}})}catch{this._synchronizationFailed=!0}finally{this._synchronizingTo=void 0}}}_positionSummary(t){return(t.upperMotor===t.lowerMotor?[t.upperMotor]:[t.upperMotor,t.lowerMotor]).map(i=>{let s=this._readout(i);return s?`${this._motorName(i)} ${s}`:this._motorName(i)}).join(" \xB7 ")}_combinedLighting(t,e){if(this._hasLighting(t))return l;let i=e.map(_=>this._mainLight(_.bed)).filter(_=>_!==void 0);if(i.length===0)return l;let s=i.filter(_=>this._state(_)?.state==="on").length,r=s===i.length,a=s>0,c=r?"combined.on":a?"combined.mixed":"combined.off",p=h(this.hass,"combined.lights");return d`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${a?"active":""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${p}</span>
          <span class="secondary">${h(this.hass,c)}</span>
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
    `}_combinedBluetooth(t){let e=t.filter(i=>i.bed.connectivity).map(i=>({pane:i,entityId:i.bed.connectivity}));return e.length===0?l:d`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${e.map(({pane:i,entityId:s})=>{let r=this._connectionStatus(i.bed),c=this._state(s)?.attributes.rssi;return d`
            <button
              class="bluetooth-status ${r}"
              @click=${()=>this._moreInfo(s)}
            >
              <ha-icon
                icon=${r==="connected"?"mdi:bluetooth-connect":r==="connecting"?"mdi:bluetooth-transfer":r==="idle"?"mdi:bluetooth":"mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${i.label}</span>
                <span class="bluetooth-detail">
                  ${h(this.hass,`status.${r}`)}${typeof c=="number"?` \xB7 ${c} dBm`:""}
                </span>
              </span>
            </button>
          `})}
      </div>
    `}_mainLight(t){return t.lights.light??t.lights.switch}_hasLighting(t){let e=t.lights;return!!(e.light||e.switch||e.level||e.timer||e.toggle||e.cycle)}_deviceLabel(t){let e=this.hass?.devices[t];return e?.name_by_user??e?.name??t}_orderedSections(){let t=this._config?.section_order;if(!t?.length)return[...N];let e=new Set(N),i=t.filter(r=>e.has(r)),s=N.filter(r=>!i.includes(r));return[...i,...s]}_header(t,e){let i=this._connectionStatus(t),s={connected:{cls:"ok",icon:"mdi:bluetooth-connect",key:"status.connected"},connecting:{cls:"connecting",icon:"mdi:bluetooth-transfer",key:"status.connecting"},idle:{cls:"idle",icon:"mdi:bluetooth",key:"status.idle"},disconnected:{cls:"off",icon:"mdi:bluetooth-off",key:"status.disconnected"}};return d`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(e)}</span>
        ${i===void 0?l:d`
                <button
                  class="conn ${s[i].cls}"
                  @click=${()=>this._moreInfo(t.connectivity)}
                  title=${h(this.hass,s[i].key)}
                >
                  <ha-icon icon=${s[i].icon}></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(t,e="theme"){let i=this._graphicState(t);return i?d`
      <div class="graphic">
        ${Pt(i,e)}
      </div>
    `:l}_graphicState(t){let e=t.motors.filter(c=>{let p=c.angle??c.position;return p!==void 0&&this._state(p)?.attributes.unit_of_measurement==="\xB0"});if(e.length===0||e.some(c=>this._angle(c)===void 0))return;let i=Mt(e);if(!i)return;let{upper:s,lower:r}=i,a=t.motors.some(c=>{let p=c.cover?this._state(c.cover)?.state:void 0;return p==="opening"||p==="closing"});return{upperMotor:s,lowerMotor:r,upper:{label:this._motorName(s),angle:this._angle(s)},lower:{label:this._motorName(r),angle:this._angle(r)},moving:a}}_motors(t){let e=t.motors.filter(r=>r.cover||r.up||r.down),i=t.motors.filter(r=>r.position&&!r.cover&&!r.up&&!r.down);if(e.length===0&&i.length===0&&!t.synchro&&!t.stop)return l;let s=e.length>0||i.length>0||!!t.synchro;return d`
      ${s?this._heading("section.position"):l}
      ${t.synchro?this._toggleRow(t.synchro):l}
      ${e.length?d`<div class="rows">
              ${e.map(r=>this._motorRow(r,t.stop))}
            </div>`:l}
      ${i.length?d`<div class="rows">
              ${i.map(r=>this._moreInfoRow(r.position))}
            </div>`:l}
      ${t.stop?d`<button class="stop-all" @click=${()=>this._hold.stopAll(t.stop)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${h(this.hass,"action.stop_all")}</span>
            </button>`:l}
    `}_firmness(t){return t.firmness.length===0?l:d`
      ${this._heading("section.firmness")}
      <div class="rows">${t.firmness.map(e=>this._moreInfoRow(e))}</div>
    `}_motorRow(t,e){let i=this._readout(t),s=t.cover??t.up,r=t.cover??t.down,a=!!t.cover||!!e,c=d`
      <span>${this._motorName(t)}</span>
      ${i?d`<span class="readout">${i}</span>`:l}
    `;return d`
      <div class="row">
        ${t.position?d`<button
              class="row-label position-label"
              aria-label=${this._name(t.position)}
              @click=${()=>this._moreInfo(t.position)}
            >${c}</button>`:d`<div class="row-label">${c}</div>`}
        <div class="control-group">
          <button
            class="cg-btn"
            aria-label=${h(this.hass,"action.up")}
            @pointerdown=${p=>this._startHold(p,t,"up",e)}
            @pointerup=${p=>this._endPointerHold(p,t)}
            @pointercancel=${p=>this._endPointerHold(p,t)}
            @keydown=${p=>this._startHold(p,t,"up",e)}
            @keyup=${p=>this._endKeyHold(p,t)}
            @blur=${()=>this._endHold(t)}
            @click=${p=>this._activateWithoutPointer(p,t,"up",e)}
            ?disabled=${!s||this._config?.layout==="compact"&&(!a||!this._available(s))}
          >
            <ha-icon icon="mdi:chevron-up"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${h(this.hass,"action.stop")}
            @click=${()=>this._motorStop(t,e)}
            ?disabled=${!a}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${h(this.hass,"action.down")}
            @pointerdown=${p=>this._startHold(p,t,"down",e)}
            @pointerup=${p=>this._endPointerHold(p,t)}
            @pointercancel=${p=>this._endPointerHold(p,t)}
            @keydown=${p=>this._startHold(p,t,"down",e)}
            @keyup=${p=>this._endKeyHold(p,t)}
            @blur=${()=>this._endHold(t)}
            @click=${p=>this._activateWithoutPointer(p,t,"down",e)}
            ?disabled=${!r||this._config?.layout==="compact"&&(!a||!this._available(r))}
          >
            <ha-icon icon="mdi:chevron-down"></ha-icon>
          </button>
        </div>
      </div>
    `}_presets(t){return t.presets.length===0?l:d`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${t.presets.map(e=>this._tile(e,()=>this._press(e)))}
      </div>
    `}_utility(t){return t.utility.length===0?l:d`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${t.utility.map(e=>this._tile(e,()=>e.startsWith("switch.")?this._call("switch","toggle",e):this._press(e)))}
      </div>
    `}_memory(t){let e=t.memory,i=this._config?.memory_slots;if(i&&i.length){let c=new Set(i.map(Number));e=e.filter(p=>c.has(p.slot))}if(e.length===0)return l;let s=this._config?.memory_save!==!1&&e.some(c=>c.save),r=e.map(c=>c.save??c.goto??String(c.slot)).join("|"),a=this._saveModeFor===r;return d`
      <div class="section-heading heading-row">
        <span>${h(this.hass,"section.memory")}</span>
        ${s?d`<button
                class="set-btn ${a?"active":""}"
                @click=${()=>this._toggleSaveMode(r)}
              >
                <ha-icon
                  icon=${a?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${h(this.hass,a?"memory.cancel":"memory.set")}</span>
              </button>`:l}
      </div>
      ${a?d`<div class="hint">${h(this.hass,"memory.set_hint")}</div>`:l}
      <div class="tiles">${e.map(c=>this._memoryTile(c,a))}</div>
    `}_memoryTile(t,e){let i=t.goto??t.save;if(e){let r=!!t.save;return d`
        <button
          class="tile ${r?"save-mode":"is-disabled"}"
          ?disabled=${!r}
          @click=${()=>r&&this._saveMemory(t)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(i)}</span>
        </button>
      `}let s=!!t.goto;return d`
      <button
        class="tile ${s?"":"is-disabled"}"
        ?disabled=${!s}
        @click=${()=>t.goto&&this._press(t.goto)}
      >
        ${this._icon(i)}
        <span class="tile-label">${this._name(i)}</span>
      </button>
    `}_lighting(t){let e=t.lights,i=e.light??e.switch;return!i&&!e.state&&!e.level&&!e.timer&&!e.toggle&&!e.cycle?l:d`
      ${this._heading("section.lighting")}
      ${i?this._toggleRow(i):l}
      ${e.state?this._moreInfoRow(e.state):l}
      ${e.level?this._moreInfoRow(e.level):l}
      ${e.timer?this._moreInfoRow(e.timer):l}
      ${e.toggle||e.cycle?d`<div class="tiles">
              ${e.toggle?this._tile(e.toggle,()=>this._press(e.toggle)):l}
              ${e.cycle?this._tile(e.cycle,()=>this._press(e.cycle)):l}
            </div>`:l}
    `}_massage(t){let e=t.massage;return e.buttons.length===0&&e.numbers.length===0&&!e.timer?l:d`
      ${this._heading("section.massage")}
      ${e.buttons.length?d`<div class="tiles">
              ${e.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:l}
      ${e.numbers.map(i=>this._moreInfoRow(i))}
      ${e.timer?this._moreInfoRow(e.timer):l}
    `}_climate(t){let e=[...t.climate.entities,...t.climate.selects];return e.length===0?l:d`
      ${this._heading("section.climate")}
      ${e.map(i=>this._moreInfoRow(i))}
    `}_connection(t){return!t.connect&&!t.disconnect?l:d`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${t.connect?this._tile(t.connect,()=>this._press(t.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):l}
        ${t.disconnect?this._tile(t.disconnect,()=>this._press(t.disconnect),{icon:"mdi:bluetooth-off"}):l}
      </div>
    `}_heading(t){return d`<div class="section-heading">${h(this.hass,t)}</div>`}_tile(t,e,i={}){return d`
      <button class="tile ${i.cls??""}" @click=${e}>
        ${this._icon(t,i.icon)}
        <span class="tile-label">${this._name(t)}</span>
      </button>
    `}_onRowKey(t,e){t.target===t.currentTarget&&(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),e())}_toggleRow(t){let i=this._state(t)?.state==="on",s=this._name(t);return d`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${s}
        @click=${()=>this._moreInfo(t)}
        @keydown=${r=>this._onRowKey(r,()=>this._moreInfo(t))}
      >
        ${this._icon(t)}
        <div class="entity-row-text">
          <span>${s}</span>
          <span class="secondary">${this._stateText(t)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-label=${s}
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(t)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(t){let e=this._name(t);return d`
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
    `}_icon(t,e){let i=this._state(t);return i?d`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:d`<ha-icon class="icon" icon=${e??"mdi:bed"}></ha-icon>`}_notice(t){return d`<ha-card><div class="notice">${h(this.hass,t)}</div></ha-card>`}_state(t){return this.hass?.states[t]}_title(t){return this._config?.name?this._config.name:this._deviceName(t)??h(this.hass,"card.default_name")}_deviceName(t=this._config?.device_id){let e=t?this.hass?.devices[t]:void 0;return e?.name_by_user||e?.name||void 0}_name(t){let e=this._state(t)?.attributes.friendly_name??this.hass?.entities[t]?.name??t,i=this.hass?.entities[t]?.device_id,s=this._deviceName(i);return s&&e.startsWith(s+" ")?e.slice(s.length+1):e}_motorName(t){let e=`motor.${t.key}`,i=h(this.hass,e);return i!==e?i:t.key.split("_").map(s=>s.charAt(0).toUpperCase()+s.slice(1)).join(" ")}_angle(t){let e=t.angle??t.position;if(!e)return;let i=Number.parseFloat(this._state(e)?.state??"");return Number.isFinite(i)?i:void 0}_readout(t){let e=t.angle??t.position;if(e){let i=this._angle(t);if(i===void 0)return;let s=this._state(e)?.attributes.unit_of_measurement,r=t.angle?"\xB0":"%";return`${Math.round(i)}${typeof s=="string"?s:r}`}if(t.cover){let i=this._state(t.cover)?.attributes.current_position;return typeof i=="number"?`${Math.round(i)}%`:void 0}}_stateText(t){let e=this._state(t);if(!e)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(e):e.state}_collectWatched(t){let e=new Set;for(let i of t.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(s=>s&&e.add(s));t.presets.forEach(i=>e.add(i));for(let i of t.memory)[i.goto,i.save].forEach(s=>s&&e.add(s));return[t.stop,t.synchro,t.connect,t.disconnect,t.connectivity,t.lights.light,t.lights.switch,t.lights.state,t.lights.level,t.lights.toggle,t.lights.cycle,t.lights.timer,t.massage.timer].forEach(i=>i&&e.add(i)),t.firmness.forEach(i=>e.add(i)),t.massage.buttons.forEach(i=>e.add(i)),t.massage.numbers.forEach(i=>e.add(i)),t.utility.forEach(i=>e.add(i)),t.climate.entities.forEach(i=>e.add(i)),t.climate.selects.forEach(i=>e.add(i)),[...e]}_startHold(t,e,i,s){let r=null;if(t instanceof KeyboardEvent){if(t.repeat||t.key!=="Enter"&&t.key!==" ")return;t.preventDefault()}else{if(t.button!==0||!t.isPrimary)return;t.currentTarget.setPointerCapture?.(t.pointerId),t.preventDefault(),r=t.pointerId}this._config?.layout==="compact"&&(s?this._compactStopTargets.add(s):e.cover&&this._compactStopTargets.add(e.cover),this.requestUpdate()),this._hold.start(e,i,r,s)}_activateWithoutPointer(t,e,i,s){if(t.detail!==0||this._hold.heldKey!==null)return;if(this._config?.layout==="compact"&&(s?this._compactStopTargets.add(s):e.cover&&this._compactStopTargets.add(e.cover),this.requestUpdate()),e.cover){this._cover(e.cover,i==="up"?"open_cover":"close_cover");return}let r=i==="up"?e.up:e.down;r&&this._press(r)}_endPointerHold(t,e){this._hold.endFromPointer(e,t.pointerId,t.type!=="pointerup"||t.button===0)}_endKeyHold(t,e){t.key!=="Enter"&&t.key!==" "||this._hold.end(e)}_endHold(t){this._hold.end(t)}_motorStop(t,e){if(t.cover){this._hold.cancel(t),this._cover(t.cover,"stop_cover");return}this._hold.stopAll(e)}_toggleSaveMode(t){this._saveModeFor=this._saveModeFor===t?void 0:t}_saveMemory(t){t.save&&this._press(t.save),this._saveModeFor=void 0}_call(t,e,i){this.hass?.callService(t,e,{entity_id:i})?.catch(()=>{})}_press(t){this._call("button","press",t)}_cover(t,e){this._call("cover",e,t)}_toggle(t){this._call("homeassistant","toggle",t)}_setEntities(t,e){this.hass?.callService("homeassistant",e?"turn_on":"turn_off",{entity_id:t})?.catch(()=>{})}_moreInfo(t){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:t},bubbles:!0,composed:!0}))}};k.styles=W`
    .compact-card { container-type: inline-size; padding: 12px; }
    .compact-header { display: flex; align-items: center; gap: 8px; min-height: 32px; }
    .compact-header .title { font-size: .95rem; }
    .compact-open { border: 0; background: none; color: var(--secondary-text-color);
      cursor: pointer; min-width: 44px; min-height: 44px; }
    .compact-open ha-icon { --mdc-icon-size: 18px; }
    .compact-card .compact-tabs { display: flex; flex-wrap: wrap; margin: 6px 0; }
    .compact-tabs .pane-tab { flex: 1 1 65px; min-height: 44px; padding: 4px 6px; }
    .compact-tabs .pane-tab span { white-space: normal; overflow-wrap: anywhere; }
    .compact-target { color: var(--secondary-text-color); font-size: .8rem; padding: 6px 0; }
    .compact-graphic { display: block; box-sizing: border-box; width: 100%; padding: 0;
      border: 0; border-radius: 8px; background: none; color: var(--primary-text-color); }
    button.compact-graphic { cursor: pointer; }
    .compact-graphic .bed-graphic { width: 100%; height: 125px; max-width: 300px; margin: auto; }
    .compact-glance .compact-graphic .bed-graphic { height: 90px; }
    .compact-no-position { min-height: 90px; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 8px; font-size: .75rem;
      color: var(--secondary-text-color); }
    .compact-no-position ha-icon { --mdc-icon-size: 36px; }
    .compact-readouts { display: flex; gap: 8px; margin: 0 0 10px; }
    .compact-readouts > div { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
    .compact-side-name { display: flex; align-items: center; gap: 5px; font-size: .75rem;
      color: var(--primary-text-color); overflow-wrap: anywhere; }
    .compact-position { font-size: .68rem; color: var(--secondary-text-color); overflow-wrap: anywhere; }
    .side-theme .dual-swatch { background: var(--primary-color); }
    .compact-card .compact-actions { grid-template-columns: repeat(auto-fit, minmax(64px, 1fr)); gap: 6px; }
    .compact-actions .tile { min-height: 54px; padding: 7px 4px; }
    .compact-actions .tile-label { font-size: .75rem; white-space: normal; overflow-wrap: anywhere; }
    .compact-stop ha-icon { color: var(--error-color); }
    .compact-actions .tile:disabled { opacity: .45; cursor: default; }
    .compact-motors { margin-bottom: 10px; }
    .compact-motors .row { flex-wrap: wrap; }
    .compact-motors .cg-btn { min-width: 44px; min-height: 44px; }
    .compact-connections { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px;
      font-size: .72rem; color: var(--secondary-text-color); }
    .compact-connections > span { display: inline-flex; align-items: center; gap: 5px; }
    .no-animation .bed-panel, .no-animation .dual-bed-panel { transition: none; }
    button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    @container (max-width: 230px) {
      .compact-motors .row-label { flex-basis: 100%; }
      .compact-motors .control-group { width: 100%; }
      .compact-graphic .bed-graphic { height: 105px; }
    }
    @media (prefers-reduced-motion: reduce) {
      :host .bed-panel, :host .dual-bed-panel { transition: none; }
    }

    :host {
      --ab-gap: 10px;
      --ab-side-left-rgb: 75, 0, 255;
      --ab-side-right-rgb: 234, 65, 65;
    }
    ha-card {
      padding: 12px 12px 16px;
      overflow: hidden;
    }
    .header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 4px 8px;
    }
    .header-icon {
      color: var(--state-icon-color, var(--primary-text-color));
      --mdc-icon-size: 22px;
    }
    .title {
      font-size: 1.1rem;
      font-weight: 500;
      color: var(--primary-text-color);
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .conn {
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
    .pane-tabs {
      display: grid;
      grid-template-columns: repeat(var(--pane-count, 3), minmax(0, 1fr));
      gap: 4px;
      padding: 4px;
      margin: 0 0 6px;
      border-radius: 14px;
      background: var(--secondary-background-color);
    }
    .pane-tab {
      min-width: 0;
      height: 42px;
      padding: 0 8px;
      border: 0;
      border-radius: 11px;
      background: transparent;
      color: var(--secondary-text-color);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      font: inherit;
      font-size: 0.82rem;
      font-weight: 500;
      transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
      -webkit-user-select: none;
      user-select: none;
      touch-action: manipulation;
    }
    .pane-tab ha-icon {
      --mdc-icon-size: 19px;
      flex: none;
    }
    .pane-tab span:not(.connection-dot) {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pane-tab:hover {
      color: var(--primary-text-color);
    }
    .pane-tab.active {
      color: var(--primary-text-color);
      background: var(--card-background-color);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.14);
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
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
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
      opacity: 0.78;
      stroke: var(--primary-text-color);
      stroke-opacity: 0.14;
      stroke-width: 1px;
      vector-effect: non-scaling-stroke;
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
      stroke-opacity: 0.1;
      stroke-width: 1px;
      vector-effect: non-scaling-stroke;
    }
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
      border-radius: 10px;
      background: var(--secondary-background-color);
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
      border: 1px solid var(--divider-color);
      border-radius: 11px;
      background: var(--card-background-color);
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
      border: 1px solid var(--divider-color);
      border-radius: 9px;
      background: var(--secondary-background-color);
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
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      padding: 8px 12px;
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
    .control-group {
      display: inline-flex;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--divider-color);
    }
    .cg-btn {
      border: none;
      background: var(--card-background-color);
      color: var(--primary-color);
      cursor: pointer;
      padding: 8px 14px;
      display: inline-flex;
      align-items: center;
      --mdc-icon-size: 22px;
      transition: background 0.15s ease;
      /* Press-and-hold has to survive a slightly unsteady finger. Pointer
         capture and preventDefault() do not override the browser's touch
         gesture arbitration, so without this a small vertical drag starts
         scrolling the page, fires pointercancel and cuts the hold short. */
      touch-action: none;
    }
    .cg-btn:not(:last-child) {
      border-right: 1px solid var(--divider-color);
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
      border-radius: 12px;
      cursor: pointer;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
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
      gap: 6px;
      padding: 14px 6px 10px;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
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
      --mdc-icon-size: 24px;
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
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
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
    .bluetooth-status {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      background: var(--card-background-color);
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
  `,x([U({attribute:!1})],k.prototype,"hass",2),x([C()],k.prototype,"_config",2),x([C()],k.prototype,"_saveModeFor",2),x([C()],k.prototype,"_activePairedPane",2),x([C()],k.prototype,"_synchronizingTo",2),x([C()],k.prototype,"_synchronizationFailed",2);customElements.get("adjustable-bed-card")||customElements.define("adjustable-bed-card",k);console.info(`%c adjustable-bed-card %c ${oe} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{k as AdjustableBedCard};
