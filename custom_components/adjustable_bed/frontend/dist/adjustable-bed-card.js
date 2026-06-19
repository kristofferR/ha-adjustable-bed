/* adjustable-bed-card 2.9.14 — ships with the Adjustable Bed integration. Do not edit; build from frontend/src. */
var Le=Object.defineProperty;var Ue=Object.getOwnPropertyDescriptor;var y=(o,s,e,t)=>{for(var i=t>1?void 0:t?Ue(s,e):s,r=o.length-1,n;r>=0;r--)(n=o[r])&&(i=(t?n(s,e,i):n(i))||i);return t&&i&&Le(s,e,i),i};var F=globalThis,V=F.ShadowRoot&&(F.ShadyCSS===void 0||F.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Q=Symbol(),ge=new WeakMap,H=class{constructor(s,e,t){if(this._$cssResult$=!0,t!==Q)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=s,this.t=e}get styleSheet(){let s=this.o,e=this.t;if(V&&s===void 0){let t=e!==void 0&&e.length===1;t&&(s=ge.get(e)),s===void 0&&((this.o=s=new CSSStyleSheet).replaceSync(this.cssText),t&&ge.set(e,s))}return s}toString(){return this.cssText}},me=o=>new H(typeof o=="string"?o:o+"",void 0,Q),N=(o,...s)=>{let e=o.length===1?o[0]:s.reduce((t,i,r)=>t+(n=>{if(n._$cssResult$===!0)return n.cssText;if(typeof n=="number")return n;throw Error("Value passed to 'css' function must be a 'css' function result: "+n+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+o[r+1],o[0]);return new H(e,o,Q)},ue=(o,s)=>{if(V)o.adoptedStyleSheets=s.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of s){let t=document.createElement("style"),i=F.litNonce;i!==void 0&&t.setAttribute("nonce",i),t.textContent=e.cssText,o.appendChild(t)}},Y=V?o=>o:o=>o instanceof CSSStyleSheet?(s=>{let e="";for(let t of s.cssRules)e+=t.cssText;return me(e)})(o):o;var{is:De,defineProperty:ze,getOwnPropertyDescriptor:Ie,getOwnPropertyNames:qe,getOwnPropertySymbols:Fe,getPrototypeOf:Ve}=Object,W=globalThis,fe=W.trustedTypes,We=fe?fe.emptyScript:"",Ge=W.reactiveElementPolyfillSupport,B=(o,s)=>o,j={toAttribute(o,s){switch(s){case Boolean:o=o?We:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,s){let e=o;switch(s){case Boolean:e=o!==null;break;case Number:e=o===null?null:Number(o);break;case Object:case Array:try{e=JSON.parse(o)}catch{e=null}}return e}},G=(o,s)=>!De(o,s),_e={attribute:!0,type:String,converter:j,reflect:!1,useDefault:!1,hasChanged:G};Symbol.metadata??=Symbol("metadata"),W.litPropertyMetadata??=new WeakMap;var b=class extends HTMLElement{static addInitializer(s){this._$Ei(),(this.l??=[]).push(s)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(s,e=_e){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(s)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(s,e),!e.noAccessor){let t=Symbol(),i=this.getPropertyDescriptor(s,t,e);i!==void 0&&ze(this.prototype,s,i)}}static getPropertyDescriptor(s,e,t){let{get:i,set:r}=Ie(this.prototype,s)??{get(){return this[e]},set(n){this[e]=n}};return{get:i,set(n){let a=i?.call(this);r?.call(this,n),this.requestUpdate(s,a,t)},configurable:!0,enumerable:!0}}static getPropertyOptions(s){return this.elementProperties.get(s)??_e}static _$Ei(){if(this.hasOwnProperty(B("elementProperties")))return;let s=Ve(this);s.finalize(),s.l!==void 0&&(this.l=[...s.l]),this.elementProperties=new Map(s.elementProperties)}static finalize(){if(this.hasOwnProperty(B("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(B("properties"))){let e=this.properties,t=[...qe(e),...Fe(e)];for(let i of t)this.createProperty(i,e[i])}let s=this[Symbol.metadata];if(s!==null){let e=litPropertyMetadata.get(s);if(e!==void 0)for(let[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let i=this._$Eu(e,t);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(s){let e=[];if(Array.isArray(s)){let t=new Set(s.flat(1/0).reverse());for(let i of t)e.unshift(Y(i))}else s!==void 0&&e.push(Y(s));return e}static _$Eu(s,e){let t=e.attribute;return t===!1?void 0:typeof t=="string"?t:typeof s=="string"?s.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(s=>this.enableUpdating=s),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(s=>s(this))}addController(s){(this._$EO??=new Set).add(s),this.renderRoot!==void 0&&this.isConnected&&s.hostConnected?.()}removeController(s){this._$EO?.delete(s)}_$E_(){let s=new Map,e=this.constructor.elementProperties;for(let t of e.keys())this.hasOwnProperty(t)&&(s.set(t,this[t]),delete this[t]);s.size>0&&(this._$Ep=s)}createRenderRoot(){let s=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return ue(s,this.constructor.elementStyles),s}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(s=>s.hostConnected?.())}enableUpdating(s){}disconnectedCallback(){this._$EO?.forEach(s=>s.hostDisconnected?.())}attributeChangedCallback(s,e,t){this._$AK(s,t)}_$ET(s,e){let t=this.constructor.elementProperties.get(s),i=this.constructor._$Eu(s,t);if(i!==void 0&&t.reflect===!0){let r=(t.converter?.toAttribute!==void 0?t.converter:j).toAttribute(e,t.type);this._$Em=s,r==null?this.removeAttribute(i):this.setAttribute(i,r),this._$Em=null}}_$AK(s,e){let t=this.constructor,i=t._$Eh.get(s);if(i!==void 0&&this._$Em!==i){let r=t.getPropertyOptions(i),n=typeof r.converter=="function"?{fromAttribute:r.converter}:r.converter?.fromAttribute!==void 0?r.converter:j;this._$Em=i;let a=n.fromAttribute(e,r.type);this[i]=a??this._$Ej?.get(i)??a,this._$Em=null}}requestUpdate(s,e,t,i=!1,r){if(s!==void 0){let n=this.constructor;if(i===!1&&(r=this[s]),t??=n.getPropertyOptions(s),!((t.hasChanged??G)(r,e)||t.useDefault&&t.reflect&&r===this._$Ej?.get(s)&&!this.hasAttribute(n._$Eu(s,t))))return;this.C(s,e,t)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(s,e,{useDefault:t,reflect:i,wrapped:r},n){t&&!(this._$Ej??=new Map).has(s)&&(this._$Ej.set(s,n??e??this[s]),r!==!0||n!==void 0)||(this._$AL.has(s)||(this.hasUpdated||t||(e=void 0),this._$AL.set(s,e)),i===!0&&this._$Em!==s&&(this._$Eq??=new Set).add(s))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let s=this.scheduleUpdate();return s!=null&&await s,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,r]of this._$Ep)this[i]=r;this._$Ep=void 0}let t=this.constructor.elementProperties;if(t.size>0)for(let[i,r]of t){let{wrapped:n}=r,a=this[i];n!==!0||this._$AL.has(i)||a===void 0||this.C(i,void 0,r,a)}}let s=!1,e=this._$AL;try{s=this.shouldUpdate(e),s?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(t){throw s=!1,this._$EM(),t}s&&this._$AE(e)}willUpdate(s){}_$AE(s){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(s)),this.updated(s)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(s){return!0}update(s){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(s){}firstUpdated(s){}};b.elementStyles=[],b.shadowRootOptions={mode:"open"},b[B("elementProperties")]=new Map,b[B("finalized")]=new Map,Ge?.({ReactiveElement:b}),(W.reactiveElementVersions??=[]).push("2.1.2");var ne=globalThis,ve=o=>o,K=ne.trustedTypes,ye=K?K.createPolicy("lit-html",{createHTML:o=>o}):void 0,Ae="$lit$",$=`lit$${Math.random().toFixed(9).slice(2)}$`,Se="?"+$,Ke=`<${Se}>`,S=document,U=()=>S.createComment(""),D=o=>o===null||typeof o!="object"&&typeof o!="function",ae=Array.isArray,Je=o=>ae(o)||typeof o?.[Symbol.iterator]=="function",ee=`[ 	
\f\r]`,L=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,be=/-->/g,$e=/>/g,E=RegExp(`>|${ee}(?:([^\\s"'>=/]+)(${ee}*=${ee}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),xe=/'/g,we=/"/g,ke=/^(?:script|style|textarea|title)$/i,ce=o=>(s,...e)=>({_$litType$:o,strings:s,values:e}),p=ce(1),Ce=ce(2),ft=ce(3),k=Symbol.for("lit-noChange"),l=Symbol.for("lit-nothing"),Ee=new WeakMap,A=S.createTreeWalker(S,129);function Re(o,s){if(!ae(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return ye!==void 0?ye.createHTML(s):s}var Xe=(o,s)=>{let e=o.length-1,t=[],i,r=s===2?"<svg>":s===3?"<math>":"",n=L;for(let a=0;a<e;a++){let d=o[a],m,u,c=-1,h=0;for(;h<d.length&&(n.lastIndex=h,u=n.exec(d),u!==null);)h=n.lastIndex,n===L?u[1]==="!--"?n=be:u[1]!==void 0?n=$e:u[2]!==void 0?(ke.test(u[2])&&(i=RegExp("</"+u[2],"g")),n=E):u[3]!==void 0&&(n=E):n===E?u[0]===">"?(n=i??L,c=-1):u[1]===void 0?c=-2:(c=n.lastIndex-u[2].length,m=u[1],n=u[3]===void 0?E:u[3]==='"'?we:xe):n===we||n===xe?n=E:n===be||n===$e?n=L:(n=E,i=void 0);let _=n===E&&o[a+1].startsWith("/>")?" ":"";r+=n===L?d+Ke:c>=0?(t.push(m),d.slice(0,c)+Ae+d.slice(c)+$+_):d+$+(c===-2?a:_)}return[Re(o,r+(o[e]||"<?>")+(s===2?"</svg>":s===3?"</math>":"")),t]},z=class o{constructor({strings:s,_$litType$:e},t){let i;this.parts=[];let r=0,n=0,a=s.length-1,d=this.parts,[m,u]=Xe(s,e);if(this.el=o.createElement(m,t),A.currentNode=this.el.content,e===2||e===3){let c=this.el.content.firstChild;c.replaceWith(...c.childNodes)}for(;(i=A.nextNode())!==null&&d.length<a;){if(i.nodeType===1){if(i.hasAttributes())for(let c of i.getAttributeNames())if(c.endsWith(Ae)){let h=u[n++],_=i.getAttribute(c).split($),g=/([.?@])?(.*)/.exec(h);d.push({type:1,index:r,name:g[2],strings:_,ctor:g[1]==="."?se:g[1]==="?"?ie:g[1]==="@"?oe:T}),i.removeAttribute(c)}else c.startsWith($)&&(d.push({type:6,index:r}),i.removeAttribute(c));if(ke.test(i.tagName)){let c=i.textContent.split($),h=c.length-1;if(h>0){i.textContent=K?K.emptyScript:"";for(let _=0;_<h;_++)i.append(c[_],U()),A.nextNode(),d.push({type:2,index:++r});i.append(c[h],U())}}}else if(i.nodeType===8)if(i.data===Se)d.push({type:2,index:r});else{let c=-1;for(;(c=i.data.indexOf($,c+1))!==-1;)d.push({type:7,index:r}),c+=$.length-1}r++}}static createElement(s,e){let t=S.createElement("template");return t.innerHTML=s,t}};function M(o,s,e=o,t){if(s===k)return s;let i=t!==void 0?e._$Co?.[t]:e._$Cl,r=D(s)?void 0:s._$litDirective$;return i?.constructor!==r&&(i?._$AO?.(!1),r===void 0?i=void 0:(i=new r(o),i._$AT(o,e,t)),t!==void 0?(e._$Co??=[])[t]=i:e._$Cl=i),i!==void 0&&(s=M(o,i._$AS(o,s.values),i,t)),s}var te=class{constructor(s,e){this._$AV=[],this._$AN=void 0,this._$AD=s,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(s){let{el:{content:e},parts:t}=this._$AD,i=(s?.creationScope??S).importNode(e,!0);A.currentNode=i;let r=A.nextNode(),n=0,a=0,d=t[0];for(;d!==void 0;){if(n===d.index){let m;d.type===2?m=new I(r,r.nextSibling,this,s):d.type===1?m=new d.ctor(r,d.name,d.strings,this,s):d.type===6&&(m=new re(r,this,s)),this._$AV.push(m),d=t[++a]}n!==d?.index&&(r=A.nextNode(),n++)}return A.currentNode=S,i}p(s){let e=0;for(let t of this._$AV)t!==void 0&&(t.strings!==void 0?(t._$AI(s,t,e),e+=t.strings.length-2):t._$AI(s[e])),e++}},I=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(s,e,t,i){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=s,this._$AB=e,this._$AM=t,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let s=this._$AA.parentNode,e=this._$AM;return e!==void 0&&s?.nodeType===11&&(s=e.parentNode),s}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(s,e=this){s=M(this,s,e),D(s)?s===l||s==null||s===""?(this._$AH!==l&&this._$AR(),this._$AH=l):s!==this._$AH&&s!==k&&this._(s):s._$litType$!==void 0?this.$(s):s.nodeType!==void 0?this.T(s):Je(s)?this.k(s):this._(s)}O(s){return this._$AA.parentNode.insertBefore(s,this._$AB)}T(s){this._$AH!==s&&(this._$AR(),this._$AH=this.O(s))}_(s){this._$AH!==l&&D(this._$AH)?this._$AA.nextSibling.data=s:this.T(S.createTextNode(s)),this._$AH=s}$(s){let{values:e,_$litType$:t}=s,i=typeof t=="number"?this._$AC(s):(t.el===void 0&&(t.el=z.createElement(Re(t.h,t.h[0]),this.options)),t);if(this._$AH?._$AD===i)this._$AH.p(e);else{let r=new te(i,this),n=r.u(this.options);r.p(e),this.T(n),this._$AH=r}}_$AC(s){let e=Ee.get(s.strings);return e===void 0&&Ee.set(s.strings,e=new z(s)),e}k(s){ae(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,t,i=0;for(let r of s)i===e.length?e.push(t=new o(this.O(U()),this.O(U()),this,this.options)):t=e[i],t._$AI(r),i++;i<e.length&&(this._$AR(t&&t._$AB.nextSibling,i),e.length=i)}_$AR(s=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);s!==this._$AB;){let t=ve(s).nextSibling;ve(s).remove(),s=t}}setConnected(s){this._$AM===void 0&&(this._$Cv=s,this._$AP?.(s))}},T=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(s,e,t,i,r){this.type=1,this._$AH=l,this._$AN=void 0,this.element=s,this.name=e,this._$AM=i,this.options=r,t.length>2||t[0]!==""||t[1]!==""?(this._$AH=Array(t.length-1).fill(new String),this.strings=t):this._$AH=l}_$AI(s,e=this,t,i){let r=this.strings,n=!1;if(r===void 0)s=M(this,s,e,0),n=!D(s)||s!==this._$AH&&s!==k,n&&(this._$AH=s);else{let a=s,d,m;for(s=r[0],d=0;d<r.length-1;d++)m=M(this,a[t+d],e,d),m===k&&(m=this._$AH[d]),n||=!D(m)||m!==this._$AH[d],m===l?s=l:s!==l&&(s+=(m??"")+r[d+1]),this._$AH[d]=m}n&&!i&&this.j(s)}j(s){s===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,s??"")}},se=class extends T{constructor(){super(...arguments),this.type=3}j(s){this.element[this.name]=s===l?void 0:s}},ie=class extends T{constructor(){super(...arguments),this.type=4}j(s){this.element.toggleAttribute(this.name,!!s&&s!==l)}},oe=class extends T{constructor(s,e,t,i,r){super(s,e,t,i,r),this.type=5}_$AI(s,e=this){if((s=M(this,s,e,0)??l)===k)return;let t=this._$AH,i=s===l&&t!==l||s.capture!==t.capture||s.once!==t.once||s.passive!==t.passive,r=s!==l&&(t===l||i);i&&this.element.removeEventListener(this.name,this,t),r&&this.element.addEventListener(this.name,this,s),this._$AH=s}handleEvent(s){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,s):this._$AH.handleEvent(s)}},re=class{constructor(s,e,t){this.element=s,this.type=6,this._$AN=void 0,this._$AM=e,this.options=t}get _$AU(){return this._$AM._$AU}_$AI(s){M(this,s)}};var Ze=ne.litHtmlPolyfillSupport;Ze?.(z,I),(ne.litHtmlVersions??=[]).push("3.3.3");var Me=(o,s,e)=>{let t=e?.renderBefore??s,i=t._$litPart$;if(i===void 0){let r=e?.renderBefore??null;t._$litPart$=i=new I(s.insertBefore(U(),r),r,void 0,e??{})}return i._$AI(o),i};var le=globalThis,v=class extends b{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let s=super.createRenderRoot();return this.renderOptions.renderBefore??=s.firstChild,s}update(s){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(s),this._$Do=Me(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return k}};v._$litElement$=!0,v.finalized=!0,le.litElementHydrateSupport?.({LitElement:v});var Qe=le.litElementPolyfillSupport;Qe?.({LitElement:v});(le.litElementVersions??=[]).push("4.2.2");var J=o=>(s,e)=>{e!==void 0?e.addInitializer(()=>{customElements.define(o,s)}):customElements.define(o,s)};var Ye={attribute:!0,type:String,converter:j,reflect:!1,hasChanged:G},et=(o=Ye,s,e)=>{let{kind:t,metadata:i}=e,r=globalThis.litPropertyMetadata.get(i);if(r===void 0&&globalThis.litPropertyMetadata.set(i,r=new Map),t==="setter"&&((o=Object.create(o)).wrapped=!0),r.set(e.name,o),t==="accessor"){let{name:n}=e;return{set(a){let d=s.get.call(this);s.set.call(this,a),this.requestUpdate(n,d,o,!0,a)},init(a){return a!==void 0&&this.C(n,void 0,o,a),a}}}if(t==="setter"){let{name:n}=e;return function(a){let d=this[n];s.call(this,a),this.requestUpdate(n,d,o,!0,a)}}throw Error("Unsupported decorator location: "+t)};function P(o){return(s,e)=>typeof e=="object"?et(o,s,e):((t,i,r)=>{let n=i.hasOwnProperty(r);return i.constructor.createProperty(r,t),n?Object.getOwnPropertyDescriptor(i,r):void 0})(o,s,e)}function q(o){return P({...o,state:!0,attribute:!1})}var Te=o=>Math.max(0,Math.min(75,o));function Pe(o){let s=Te(o.upper.angle??0),e=Te(o.lower.angle??0),t=`rotate(${s} 150 70)`,i=`rotate(${-e} 150 70)`,r=n=>n.angle===void 0?"":`${n.label?n.label+" ":""}${Math.round(n.angle)}\xB0`;return Ce`
    <svg
      class="bed-graphic ${o.moving?"is-moving":""}"
      viewBox="0 0 300 110"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abMattress" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.95)" />
          <stop offset="100%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.6)" />
        </linearGradient>
        <linearGradient id="abFrame" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.45)" />
          <stop offset="100%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.2)" />
        </linearGradient>
      </defs>

      <!-- frame + legs -->
      <rect x="30" y="84" width="240" height="6" rx="3" fill="url(#abFrame)" />
      <rect x="34" y="88" width="5" height="14" rx="2" fill="url(#abFrame)" />
      <rect x="261" y="88" width="5" height="14" rx="2" fill="url(#abFrame)" />

      <!-- base mattress (static, behind the hinged panels) -->
      <rect x="42" y="64" width="216" height="20" rx="6"
        fill="rgba(var(--rgb-primary-color,33,150,243),0.28)" />

      <!-- foot panel (right of hinge) -->
      <g transform=${i} style="transition: transform 0.5s ease;">
        <rect x="150" y="58" width="108" height="18" rx="6" fill="url(#abMattress)" />
      </g>

      <!-- head/back panel (left of hinge) with pillow -->
      <g transform=${t} style="transition: transform 0.5s ease;">
        <rect x="42" y="58" width="108" height="18" rx="6" fill="url(#abMattress)" />
        <rect x="50" y="49" width="40" height="11" rx="5"
          fill="rgba(var(--rgb-primary-color,33,150,243),0.85)" />
      </g>

      <text x="86" y="22" text-anchor="middle" class="bed-graphic-label">${r(o.upper)}</text>
      <text x="214" y="22" text-anchor="middle" class="bed-graphic-label">${r(o.lower)}</text>
    </svg>
  `}var he="adjustable_bed",O=["graphic","motors","presets","memory","lighting","massage","climate","connection"],Oe=["back","legs","head","feet","lumbar","pillow","neck","tilt","hip","bed_height","stair"],de=["preset_flat","preset_zero_g","preset_anti_snore","preset_tv","preset_lounge","preset_incline","preset_both_up","preset_yoga"],tt=o=>o.split(".",1)[0],st=o=>o.translation_key??"";function it(){return{motors:[],presets:[],memory:[],presence:[],lights:{},massage:{buttons:[],numbers:[]},climate:{entities:[],selects:[]}}}function Z(o,s){let e=it();if(!s||!o?.entities)return e;let t=new Map,i=c=>{let h=t.get(c);return h||(h={key:c},t.set(c,h)),h},r=new Map,n=new Map,a=c=>{let h=n.get(c);return h||(h={slot:c},n.set(c,h)),h};for(let c of Object.values(o.entities)){if(c.device_id!==s||c.platform!==he||c.hidden)continue;let h=c.entity_id,_=tt(h),g=st(c);if(!g)continue;let w;switch(_){case"cover":i(g).cover=h;break;case"sensor":g.endsWith("_angle")&&(i(g.slice(0,-6)).angle=h);break;case"number":g.endsWith("_position")?i(g.slice(0,-9)).position=h:g.startsWith("massage_")&&g.endsWith("_intensity")&&e.massage.numbers.push(h);break;case"button":de.includes(g)||g.startsWith("preset_")?(w=g.match(/^preset_memory_(\d+)$/))?a(Number(w[1])).goto=h:r.set(g,h):(w=g.match(/^program_memory_(\d+)$/))?a(Number(w[1])).save=h:g==="stop"?e.stop=h:g==="connect"?e.connect=h:g==="disconnect"?e.disconnect=h:g==="toggle_light"?e.lights.toggle=h:g==="light_cycle"?e.lights.cycle=h:g.startsWith("massage_")?e.massage.buttons.push(h):(w=g.match(/^(.+)_(up|down)$/))&&(i(w[1])[w[2]]=h);break;case"switch":g==="under_bed_lights"&&(e.lights.switch=h);break;case"light":e.lights.light=h;break;case"binary_sensor":g==="ble_connection"?e.connectivity=h:g.startsWith("bed_presence")&&e.presence.push(h);break;case"select":g==="light_timer"?e.lights.timer=h:g==="massage_timer"?e.massage.timer=h:/thermal|footwarming|foundation/.test(g)&&e.climate.selects.push(h);break;case"climate":e.climate.entities.push(h);break}}let d=[...t.keys()],m=[...Oe.filter(c=>t.has(c)),...d.filter(c=>!Oe.includes(c)).sort()];e.motors=m.map(c=>t.get(c)).filter(c=>c.cover||c.up||c.down||c.angle||c.position);let u=[...r.keys()];return e.presets=[...de.filter(c=>r.has(c)),...u.filter(c=>!de.includes(c)).sort()].map(c=>r.get(c)),e.memory=[...n.values()].filter(c=>c.goto||c.save).sort((c,h)=>c.slot-h.slot),e}function He(o){return o.motors.length===0&&o.presets.length===0&&o.memory.length===0&&!o.stop&&!o.connect&&!o.disconnect&&!o.connectivity&&o.presence.length===0&&!o.lights.light&&!o.lights.switch&&!o.lights.toggle&&!o.lights.cycle&&o.massage.buttons.length===0&&o.massage.numbers.length===0&&o.climate.entities.length===0}var Ne={"section.position":"Position","section.presets":"Presets","section.memory":"Memory","section.lighting":"Lighting","section.massage":"Massage","section.climate":"Climate","section.connection":"Connection","action.up":"Up","action.stop":"Stop","action.down":"Down","status.connected":"Connected","status.disconnected":"Disconnected","memory.set":"Save\u2026","memory.cancel":"Cancel","memory.set_hint":"Tap a position to store the bed's current position there.","card.default_name":"Adjustable Bed","card.no_device":"Select a bed device in the card settings.","card.no_entities":"This device exposes no bed controls yet. Connect the bed and try again.","editor.device":"Bed device","editor.device_id":"Bed device","editor.name":"Card title (optional)","editor.appearance":"Sections","editor.sections":"Sections","editor.memory_group":"Memory options","editor.show_graphic":"Bed angle graphic","editor.show_motors":"Position controls","editor.show_presets":"Presets","editor.show_memory":"Memory","editor.memory_save":"Allow saving positions","editor.memory_slots":"Memory positions shown","editor.show_lighting":"Lighting","editor.show_massage":"Massage","editor.show_climate":"Climate","editor.show_connection":"Connection controls"};var Be={"section.position":"Posisjon","section.presets":"Forh\xE5ndsvalg","section.memory":"Minne","section.lighting":"Belysning","section.massage":"Massasje","section.climate":"Klima","section.connection":"Tilkobling","action.up":"Opp","action.stop":"Stopp","action.down":"Ned","status.connected":"Tilkoblet","status.disconnected":"Frakoblet","memory.set":"Lagre\u2026","memory.cancel":"Avbryt","memory.set_hint":"Trykk p\xE5 en posisjon for \xE5 lagre sengens n\xE5v\xE6rende posisjon der.","card.default_name":"Justerbar seng","card.no_device":"Velg en sengenhet i kortinnstillingene.","card.no_entities":"Denne enheten har ingen sengekontroller enn\xE5. Koble til sengen og pr\xF8v igjen.","editor.device":"Sengenhet","editor.device_id":"Sengenhet","editor.name":"Korttittel (valgfritt)","editor.appearance":"Seksjoner","editor.sections":"Seksjoner","editor.memory_group":"Minnevalg","editor.show_graphic":"Vinkelgrafikk","editor.show_motors":"Posisjonskontroller","editor.show_presets":"Forh\xE5ndsvalg","editor.show_memory":"Minne","editor.memory_save":"Tillat lagring av posisjoner","editor.memory_slots":"Minneposisjoner som vises","editor.show_lighting":"Belysning","editor.show_massage":"Massasje","editor.show_climate":"Klima","editor.show_connection":"Tilkoblingskontroller"};var C={en:Ne,nb:Be};function nt(o){let s=(o?.locale?.language||o?.language||"en").toLowerCase(),e=s.split("-")[0];return C[s]?C[s]:C[e]?C[e]:e==="nn"||e==="no"?C.nb:C.en}function f(o,s,e){let i=nt(o)[s]??C.en[s]??s;if(e)for(let[r,n]of Object.entries(e))i=i.replace(`{${r}}`,n);return i}var je="2.9.14";var at="M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z",ct="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z";function lt(o){return{graphic:o.motors.some(s=>s.angle),motors:o.motors.some(s=>s.cover||s.up||s.down)||!!o.stop,presets:o.presets.length>0,memory:o.memory.length>0,lighting:!!(o.lights.light||o.lights.switch||o.lights.toggle||o.lights.cycle),massage:o.massage.buttons.length>0||o.massage.numbers.length>0,climate:o.climate.entities.length>0||o.climate.selects.length>0,connection:!!(o.connect||o.disconnect)}}var dt=(o,s)=>o.length===s.length&&o.every((e,t)=>e===s[t]),R=class extends v{constructor(){super(...arguments);this._computeLabel=e=>f(this.hass,`editor.${e.name}`)}setConfig(e){this._config=e}_bed(){let e=this._config?.device_id;if(!(!this.hass||!e))return Z(this.hass,e)}_presentKeys(e){let t=lt(e);return O.filter(i=>t[i])}_orderedKeys(e){let t=this._presentKeys(e),r=(this._config?.section_order??[]).filter(a=>t.includes(a)),n=t.filter(a=>!r.includes(a));return[...r,...n]}_memorySlots(e){return e?e.memory.map(t=>t.slot):[]}_slotLabel(e){let t=e.goto??e.save,i=t&&this.hass?.states[t]?.attributes.friendly_name||`Memory ${e.slot}`,r=this._config?.device_id?this.hass?.devices[this._config.device_id]:void 0,n=r?.name_by_user||r?.name;return n&&i.startsWith(`${n} `)?i.slice(n.length+1):i}_emit(e){e.type=e.type??"custom:adjustable-bed-card",e.name||delete e.name,this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}get _cfg(){return{...this._config??{}}}_deviceSchema(){return[{name:"device_id",required:!0,selector:{device:{integration:"adjustable_bed"}}},{name:"name",selector:{text:{}}}]}_deviceChanged(e){e.stopPropagation();let t=e.detail.value,i=this._cfg;i.device_id=t.device_id||void 0,t.name?i.name=t.name:delete i.name,this._emit(i)}_toggleSection(e,t){let i=this._cfg;t?delete i[`show_${e}`]:i[`show_${e}`]=!1,this._emit(i)}_moveSection(e,t,i){let r=this._orderedKeys(e),n=r.indexOf(t),a=n+i;if(n<0||a<0||a>=r.length)return;[r[n],r[a]]=[r[a],r[n]];let d=this._cfg;dt(r,this._presentKeys(e))?delete d.section_order:d.section_order=r,this._emit(d)}_setMemorySave(e){let t=this._cfg;e?delete t.memory_save:t.memory_save=!1,this._emit(t)}_slotChecked(e){let t=this._config?.memory_slots;return!t||!t.length||t.map(Number).includes(e)}_toggleSlot(e,t,i){let r=this._memorySlots(e),n=this._config?.memory_slots,a=n&&n.length?n.map(Number):[...r];i?a.includes(t)||a.push(t):a=a.filter(m=>m!==t),a.sort((m,u)=>m-u);let d=this._cfg;a.length===r.length?delete d.memory_slots:d.memory_slots=a,this._emit(d)}_sectionsGroup(e){let t=this._orderedKeys(e);return t.length?p`
      <div class="group">
        <div class="group-title">${f(this.hass,"editor.sections")}</div>
        ${t.map((i,r)=>{let n=this._config?.[`show_${i}`]!==!1;return p`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${r===0}
                  @click=${()=>this._moveSection(e,i,-1)}
                  title="Move up"
                >
                  <svg viewBox="0 0 24 24"><path d=${at}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${r===t.length-1}
                  @click=${()=>this._moveSection(e,i,1)}
                  title="Move down"
                >
                  <svg viewBox="0 0 24 24"><path d=${ct}></path></svg>
                </button>
              </div>
              <span class="label">${f(this.hass,`editor.show_${i}`)}</span>
              <ha-switch
                .checked=${n}
                @change=${a=>this._toggleSection(i,a.target.checked)}
              ></ha-switch>
            </div>
          `})}
      </div>
    `:l}_memoryGroup(e){if(!(e.memory.length>0&&this._config?.show_memory!==!1))return l;let i=e.memory.some(n=>n.save),r=e.memory.length>1;return!i&&!r?l:p`
      <div class="group">
        <div class="group-title">
          ${f(this.hass,"editor.memory_group")}
        </div>
        ${i?p`<div class="row">
                <span class="label">${f(this.hass,"editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save!==!1}
                  @change=${n=>this._setMemorySave(n.target.checked)}
                ></ha-switch>
              </div>`:l}
        ${r?p`<div class="sub">
                <div class="sub-label">
                  ${f(this.hass,"editor.memory_slots")}
                </div>
                ${e.memory.map(n=>p`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(n.slot)}
                        @change=${a=>this._toggleSlot(e,n.slot,a.target.checked)}
                      ></ha-checkbox>
                      <span>${this._slotLabel(n)}</span>
                    </label>
                  `)}
              </div>`:l}
      </div>
    `}render(){if(!this.hass||!this._config)return l;let e=this._bed();return p`
      <ha-form
        .hass=${this.hass}
        .data=${{device_id:this._config.device_id,name:this._config.name}}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${e?this._sectionsGroup(e):l}
      ${e?this._memoryGroup(e):l}
    `}};R.styles=N`
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
  `,y([P({attribute:!1})],R.prototype,"hass",2),y([q()],R.prototype,"_config",2),R=y([J("adjustable-bed-card-editor")],R);var x=class extends v{constructor(){super(...arguments);this._saveMode=!1;this._watched=[]}static async getConfigElement(){return document.createElement("adjustable-bed-card-editor")}static getStubConfig(e){return{type:"custom:adjustable-bed-card",device_id:e?Object.values(e.entities).find(i=>i.platform===he)?.device_id:void 0}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 8}shouldUpdate(e){if(e.has("_config")||!e.has("hass")||!this.hass)return!0;let t=e.get("hass");if(!t||t.entities!==this.hass.entities)return!0;for(let i of this._watched)if(t.states[i]!==this.hass.states[i])return!0;return!1}render(){if(!this.hass||!this._config)return l;if(!this._config.device_id)return this._notice("card.no_device");let e=Z(this.hass,this._config.device_id);if(this._bed=e,this._watched=this._collectWatched(e),He(e))return this._notice("card.no_entities");let t=this._config,i={graphic:()=>t.show_graphic!==!1?this._graphic(e):l,motors:()=>t.show_motors!==!1?this._motors(e):l,presets:()=>t.show_presets!==!1?this._presets(e):l,memory:()=>t.show_memory!==!1?this._memory(e):l,lighting:()=>t.show_lighting!==!1?this._lighting(e):l,massage:()=>t.show_massage!==!1?this._massage(e):l,climate:()=>t.show_climate!==!1?this._climate(e):l,connection:()=>t.show_connection!==!1?this._connection(e):l};return p`
      <ha-card>
        ${this._header(e)}
        ${this._orderedSections().map(r=>i[r]?.()??l)}
      </ha-card>
    `}_orderedSections(){let e=this._config?.section_order;if(!e?.length)return[...O];let t=new Set(O),i=e.filter(n=>t.has(n)),r=O.filter(n=>!i.includes(n));return[...i,...r]}_header(e){let t=e.connectivity?this._state(e.connectivity)?.state==="on":void 0;return p`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title()}</span>
        ${t===void 0?l:p`
                <button
                  class="conn ${t?"ok":"off"}"
                  @click=${()=>this._moreInfo(e.connectivity)}
                  title=${f(this.hass,t?"status.connected":"status.disconnected")}
                >
                  <ha-icon
                    icon=${t?"mdi:bluetooth-connect":"mdi:bluetooth-off"}
                  ></ha-icon>
                </button>
              `}
      </div>
    `}_graphic(e){let t=e.motors.filter(a=>a.angle);if(t.length===0)return l;let i=e.motors.find(a=>a.key==="back")??e.motors.find(a=>a.key==="head")??t[0],r=e.motors.find(a=>a.key==="legs")??e.motors.find(a=>a.key==="feet")??t[t.length-1],n=e.motors.some(a=>{let d=a.cover?this._state(a.cover)?.state:void 0;return d==="opening"||d==="closing"});return p`
      <div class="graphic">
        ${Pe({upper:{label:this._name(i.cover??i.angle),angle:this._angle(i)},lower:{label:this._name(r.cover??r.angle),angle:this._angle(r)},moving:n})}
      </div>
    `}_motors(e){let t=e.motors.filter(i=>i.cover||i.up||i.down);return t.length===0&&!e.stop?l:p`
      ${t.length?this._heading("section.position"):l}
      ${t.length?p`<div class="rows">${t.map(i=>this._motorRow(i))}</div>`:l}
      ${e.stop?p`<button class="stop-all" @click=${()=>this._press(e.stop)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${this._name(e.stop)}</span>
            </button>`:l}
    `}_motorRow(e){let t=this._readout(e),i=e.cover??e.up,r=e.cover??e.down;return p`
      <div class="row">
        <div class="row-label">
          <span>${this._name(e.cover??e.up??e.down??e.angle??e.key)}</span>
          ${t?p`<span class="readout">${t}</span>`:l}
        </div>
        <div class="control-group">
          <button
            class="cg-btn"
            aria-label=${f(this.hass,"action.up")}
            @click=${()=>this._motorAction(e,"up")}
            ?disabled=${!i}
          >
            <ha-icon icon="mdi:chevron-up"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${f(this.hass,"action.stop")}
            @click=${()=>this._motorStop(e)}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${f(this.hass,"action.down")}
            @click=${()=>this._motorAction(e,"down")}
            ?disabled=${!r}
          >
            <ha-icon icon="mdi:chevron-down"></ha-icon>
          </button>
        </div>
      </div>
    `}_presets(e){return e.presets.length===0?l:p`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${e.presets.map(t=>this._tile(t,()=>this._press(t)))}
      </div>
    `}_memory(e){let t=e.memory,i=this._config?.memory_slots;if(i&&i.length){let n=new Set(i.map(Number));t=t.filter(a=>n.has(a.slot))}if(t.length===0)return l;let r=this._config?.memory_save!==!1&&t.some(n=>n.save);return p`
      <div class="section-heading heading-row">
        <span>${f(this.hass,"section.memory")}</span>
        ${r?p`<button
                class="set-btn ${this._saveMode?"active":""}"
                @click=${()=>this._toggleSaveMode()}
              >
                <ha-icon
                  icon=${this._saveMode?"mdi:close":"mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${f(this.hass,this._saveMode?"memory.cancel":"memory.set")}</span>
              </button>`:l}
      </div>
      ${this._saveMode?p`<div class="hint">${f(this.hass,"memory.set_hint")}</div>`:l}
      <div class="tiles">${t.map(n=>this._memoryTile(n))}</div>
    `}_memoryTile(e){let t=e.goto??e.save;if(this._saveMode){let i=!!e.save;return p`
        <button
          class="tile ${i?"save-mode":"is-disabled"}"
          ?disabled=${!i}
          @click=${()=>i&&this._saveMemory(e)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(t)}</span>
        </button>
      `}return p`
      <button class="tile" @click=${()=>this._press(t)}>
        ${this._icon(t)}
        <span class="tile-label">${this._name(t)}</span>
      </button>
    `}_lighting(e){let t=e.lights,i=t.light??t.switch;return!i&&!t.toggle&&!t.cycle?l:p`
      ${this._heading("section.lighting")}
      ${i?this._toggleRow(i):l}
      ${t.toggle||t.cycle?p`<div class="tiles">
              ${t.toggle?this._tile(t.toggle,()=>this._press(t.toggle)):l}
              ${t.cycle?this._tile(t.cycle,()=>this._press(t.cycle)):l}
            </div>`:l}
    `}_massage(e){let t=e.massage;return t.buttons.length===0&&t.numbers.length===0?l:p`
      ${this._heading("section.massage")}
      ${t.buttons.length?p`<div class="tiles">
              ${t.buttons.map(i=>this._tile(i,()=>this._press(i)))}
            </div>`:l}
      ${t.numbers.map(i=>this._moreInfoRow(i))}
      ${t.timer?this._moreInfoRow(t.timer):l}
    `}_climate(e){let t=[...e.climate.entities,...e.climate.selects];return t.length===0?l:p`
      ${this._heading("section.climate")}
      ${t.map(i=>this._moreInfoRow(i))}
    `}_connection(e){return!e.connect&&!e.disconnect?l:p`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${e.connect?this._tile(e.connect,()=>this._press(e.connect),{icon:"mdi:bluetooth-connect",cls:"success"}):l}
        ${e.disconnect?this._tile(e.disconnect,()=>this._press(e.disconnect),{icon:"mdi:bluetooth-off"}):l}
      </div>
    `}_heading(e){return p`<div class="section-heading">${f(this.hass,e)}</div>`}_tile(e,t,i={}){return p`
      <button class="tile ${i.cls??""}" @click=${t}>
        ${this._icon(e,i.icon)}
        <span class="tile-label">${this._name(e)}</span>
      </button>
    `}_toggleRow(e){let i=this._state(e)?.state==="on";return p`
      <div class="entity-row" @click=${()=>this._moreInfo(e)}>
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${this._name(e)}</span>
          <span class="secondary">${this._stateText(e)}</span>
        </div>
        <button
          class="toggle ${i?"on":""}"
          role="switch"
          aria-checked=${i?"true":"false"}
          @click=${r=>{r.stopPropagation(),this._toggle(e)}}
        >
          <span class="knob"></span>
        </button>
      </div>
    `}_moreInfoRow(e){return p`
      <div class="entity-row" @click=${()=>this._moreInfo(e)}>
        ${this._icon(e)}
        <div class="entity-row-text">
          <span>${this._name(e)}</span>
        </div>
        <span class="secondary value">${this._stateText(e)}</span>
      </div>
    `}_icon(e,t){let i=this._state(e);return i?p`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${i}
      ></ha-state-icon>`:p`<ha-icon class="icon" icon=${t??"mdi:bed"}></ha-icon>`}_notice(e){return p`<ha-card><div class="notice">${f(this.hass,e)}</div></ha-card>`}_state(e){return this.hass?.states[e]}_title(){return this._config?.name?this._config.name:this._deviceName()??f(this.hass,"card.default_name")}_deviceName(){let e=this._config?.device_id?this.hass?.devices[this._config.device_id]:void 0;return e?.name_by_user||e?.name||void 0}_name(e){let t=this._state(e)?.attributes.friendly_name??this.hass?.entities[e]?.name??e,i=this._deviceName();return i&&t.startsWith(i+" ")?t.slice(i.length+1):t}_angle(e){let t=e.angle??e.position;if(!t)return;let i=Number.parseFloat(this._state(t)?.state??"");return Number.isFinite(i)?i:void 0}_readout(e){if(e.angle){let t=this._angle(e);return t===void 0?void 0:`${Math.round(t)}\xB0`}if(e.position){let t=this._angle(e);return t===void 0?void 0:`${Math.round(t)}%`}if(e.cover){let t=this._state(e.cover)?.attributes.current_position;return typeof t=="number"?`${Math.round(t)}%`:void 0}}_stateText(e){let t=this._state(e);if(!t)return"";let i=this.hass?.formatEntityState;return typeof i=="function"?i(t):t.state}_collectWatched(e){let t=new Set;for(let i of e.motors)[i.cover,i.up,i.down,i.angle,i.position].forEach(r=>r&&t.add(r));e.presets.forEach(i=>t.add(i));for(let i of e.memory)[i.goto,i.save].forEach(r=>r&&t.add(r));return[e.stop,e.connect,e.disconnect,e.connectivity,e.lights.light,e.lights.switch,e.lights.toggle,e.lights.cycle,e.lights.timer,e.massage.timer].forEach(i=>i&&t.add(i)),e.presence.forEach(i=>t.add(i)),e.massage.buttons.forEach(i=>t.add(i)),e.massage.numbers.forEach(i=>t.add(i)),e.climate.entities.forEach(i=>t.add(i)),e.climate.selects.forEach(i=>t.add(i)),[...t]}_motorAction(e,t){if(e.cover)this._cover(e.cover,t==="up"?"open_cover":"close_cover");else{let i=t==="up"?e.up:e.down;i&&this._press(i)}}_motorStop(e){e.cover?this._cover(e.cover,"stop_cover"):this._bed?.stop&&this._press(this._bed.stop)}_toggleSaveMode(){this._saveMode=!this._saveMode}_saveMemory(e){e.save&&this._press(e.save),this._saveMode=!1}_call(e,t,i){this.hass?.callService(e,t,{entity_id:i})?.catch(()=>{})}_press(e){this._call("button","press",e)}_cover(e,t){this._call("cover",t,e)}_toggle(e){this._call("homeassistant","toggle",e)}_moreInfo(e){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:e},bubbles:!0,composed:!0}))}};x.styles=N`
    :host {
      --ab-gap: 10px;
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
      max-width: 320px;
      height: auto;
      overflow: visible;
    }
    .bed-graphic.is-moving {
      animation: ab-pulse 2s ease-in-out infinite;
    }
    .bed-graphic-label {
      fill: var(--secondary-text-color);
      font-size: 11px;
      font-family: var(--ha-font-family-body, var(--primary-font-family, sans-serif));
    }
    @keyframes ab-pulse {
      0%,
      100% {
        filter: drop-shadow(0 0 3px rgba(var(--rgb-primary-color, 33, 150, 243), 0.25));
      }
      50% {
        filter: drop-shadow(0 0 10px rgba(var(--rgb-primary-color, 33, 150, 243), 0.55));
      }
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
    .notice {
      padding: 24px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }
  `,y([P({attribute:!1})],x.prototype,"hass",2),y([q()],x.prototype,"_config",2),y([q()],x.prototype,"_saveMode",2),x=y([J("adjustable-bed-card")],x);var pe=window;pe.customCards=pe.customCards||[];pe.customCards.push({type:"adjustable-bed-card",name:"Adjustable Bed Card",description:"Native control card for the Adjustable Bed integration.",preview:!0,documentationURL:"https://github.com/kristofferR/ha-adjustable-bed"});console.info(`%c adjustable-bed-card %c ${je} `,"color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px","color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px");export{x as AdjustableBedCard};
