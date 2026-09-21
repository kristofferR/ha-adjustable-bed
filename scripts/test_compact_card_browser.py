# /// script
# dependencies = ["playwright"]
# ///
"""Exercise the shipped card in Chromium with fake HA state and recorded services.

Run after bun run check:
  uv run --no-project scripts/test_compact_card_browser.py
Set CHROMIUM_PATH if Chromium is not installed on PATH or by Playwright.
No real Home Assistant connection or device commands are used.
"""

import asyncio
import os
import shutil
from pathlib import Path

from playwright.async_api import async_playwright

BUNDLE = (
    Path(__file__).resolve().parents[1]
    / "custom_components/adjustable_bed/frontend/dist/adjustable-bed-card.js"
)
BOOT = """
customElements.define('ha-card', class extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'}).innerHTML='<style>:host{display:block;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:12px}</style><slot></slot>';}
});
customElements.define('ha-icon', class extends HTMLElement {
  static get observedAttributes(){return ['icon'];}
  connectedCallback(){this.setAttribute('aria-hidden','true');this.attributeChangedCallback();}
  attributeChangedCallback(){const name=this.getAttribute('icon')||'';this.textContent=name.includes('up')?'↑':name.includes('down')?'↓':name.includes('stop')?'■':name.includes('open-in-new')?'↗':'▱';this.style.cssText='display:inline-flex;align-items:center;justify-content:center;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);font-size:19px;line-height:1';}
});
customElements.define('ha-state-icon', class extends HTMLElement {
  set hass(value) {}
  set stateObj(value) {
    this.setAttribute('aria-hidden','true');
    this.style.cssText='display:inline-flex;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);align-items:center;justify-content:center';
    this.innerHTML='<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M3 5h2v10h16v-4H7V9h12a4 4 0 014 4v7h-2v-3H5v3H3V5m4 1h6v2H7z"/></svg>';
  }
});
window.calls = [];
window.hass = { entities: {}, devices: {}, states: {}, language: 'en',
  locale: {language: 'en'}, themes: {},
  callService: (domain, service, data) => {
    calls.push({domain, service, ...data});
    if (service === 'open_cover' || data.entity_id.endsWith('_up')) return new Promise(() => {});
    return Promise.resolve();
  }
};
for (const [id, name] of [['pair','Bed'], ['left','Left'], ['right','Right']]) {
  hass.devices[id] = {id, name, ...(id === 'pair' ? {} : {parent_device_id:'pair'})};
  const add = (domain,key,state,attrs={}) => {
    const entity_id = `${domain}.${id}_${key}`;
    hass.entities[entity_id] = {entity_id, device_id:id, translation_key:key, platform:'adjustable_bed'};
    hass.states[entity_id] = {entity_id, state, attributes:{...(id === 'pair' ? {} : {bed_side:id}),friendly_name:`${name} ${key==='preset_flat'?'Flat':key==='preset_memory_1'?'Sit':key}`, ...attrs}, last_changed:'', last_updated:''};
  };
  if (id !== 'pair') add('binary_sensor','ble_connection','off',{state_detail:'idle'});
  add('button','stop','unknown'); add('button','preset_flat','unknown');
  add('button','preset_memory_1','unknown'); add('button','program_memory_2','unknown');
  for (const motor of ['back','legs']) {
    if (id === 'pair') { add('button',`${motor}_up`,'unknown'); add('button',`${motor}_down`,'unknown'); }
    else { add('cover',motor,'open'); add('number',`${motor}_position`,motor==='back'?(id==='left'?'38':'16'):'10',{unit_of_measurement:'°'}); }
  }
}
window.card=document.createElement('adjustable-bed-card');
window.base={type:'custom:adjustable-bed-card',device_id:'pair',layout:'compact',navigation_path:'/dashboard/bed'};
card.hass=hass;card.setConfig(base);document.querySelector('main').append(card);
window.configure=async (config={})=>{card.setConfig({...base,...config});await card.updateComplete;};
"""
HTML = """<style>
body{background:#141719;color:#e8eaed;font:16px system-ui;margin:24px}
main{width:320px;max-width:100%}ha-card{display:block;border:1px solid #3a4045;border-radius:12px;background:#222629}
:root{--primary-text-color:#e8eaed;--secondary-text-color:#acb5be;--primary-color:#90c9f0;--card-background-color:#222629;--secondary-background-color:#30363d;--divider-color:#424950;--error-color:#ef9696}
</style><main></main>"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_PATH") or shutil.which("chromium"),
            headless=True,
        )
        page = await browser.new_page(viewport={"width": 900, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.route(
            "http://bed-card.test/**",
            lambda route: route.fulfill(body=HTML, content_type="text/html"),
        )
        await page.goto("http://bed-card.test/")
        await page.add_script_tag(content=BUNDLE.read_text(), type="module")
        await page.evaluate("customElements.whenDefined('adjustable-bed-card')")
        await page.evaluate(BOOT)
        card = page.locator("adjustable-bed-card")
        await card.locator(".compact-card").wait_for()
        # Optional header actions must not change title geometry or push tabs.
        measure_header = """selector => {
          const root=card.shadowRoot, header=root.querySelector(selector);
          const box=header.getBoundingClientRect(), title=header.querySelector('.title').getBoundingClientRect();
          return {height:box.height,titleX:title.x,titleY:title.y,titleWidth:title.width,
            tabsY:root.querySelector('.pane-tabs').getBoundingClientRect().y};
        }"""
        for width in [240, 400]:
            await page.locator("main").evaluate("(el,w)=>el.style.width=w+'px'", width)
            await page.evaluate("configure({layout:'full',default_target:'both'})")
            baseline = await page.evaluate(measure_header, ".header")
            for side in ["Left", "Right", "Both"]:
                await card.locator(".pane-tab").filter(has_text=side).click()
                actual = await page.evaluate(measure_header, ".header")
                assert actual == baseline, (width, side, baseline, actual)
            await page.evaluate("configure({navigation_path:undefined})")
            baseline = await page.evaluate(measure_header, ".compact-header")
            await page.evaluate("configure()")
            assert await page.evaluate(measure_header, ".compact-header") == baseline
        await page.locator("main").evaluate("el=>el.style.width='320px'")
        assert await card.locator(".dual-bed-side").count() == 2
        await card.get_by_role("button", name="Left", exact=True).click()
        assert await card.locator(".dual-bed-side").count() == 2
        await card.locator(".compact-actions .tile").first.click()
        assert (await page.evaluate("calls.at(-1).entity_id")) == "button.left_preset_flat"
        assert await page.evaluate("location.pathname") == "/"
        await card.get_by_role("button", name="Right", exact=True).click()
        await card.get_by_role("button", name="Stop", exact=True).click()
        assert await page.evaluate("calls.some(c=>c.entity_id==='button.left_stop')")
        assert await page.evaluate("calls.some(c=>c.entity_id==='button.right_stop')")

        # Failed STOP calls remain retryable after switching away from the side.
        # Successful targets clear independently, including per-cover fallbacks.
        for use_covers in [False, True]:
            failed_target = "cover.left_back" if use_covers else "button.left_stop"
            await page.evaluate(
                """async ({useCovers, failedTarget}) => {
              window.stopTestHass=hass;window.failedTarget=failedTarget;
              const entities={...hass.entities};
              if(useCovers){delete entities['button.left_stop'];delete entities['button.right_stop'];}
              let fail=true;
              hass={...hass,entities,callService:(domain,service,data)=>{
                calls.push({domain,service,...data});
                if(data.entity_id===failedTarget && fail){fail=false;return Promise.reject(new Error('BLE unavailable'));}
                return Promise.resolve();
              }};
              card.hass=hass;await configure();calls=[];
            }""",
                {"useCovers": use_covers, "failedTarget": failed_target},
            )
            await card.get_by_role("button", name="Left", exact=True).click()
            await card.locator(".compact-actions .tile").first.click()
            await card.get_by_role("button", name="Right", exact=True).click()
            await card.locator(".compact-stop").click()
            await page.evaluate("card.updateComplete")
            await card.get_by_role("button", name="Both", exact=True).click()
            await page.evaluate("calls=[]")
            await card.locator(".compact-stop").click()
            await page.evaluate("card.updateComplete")
            assert await page.evaluate("calls.map(c=>c.entity_id)") == [
                failed_target,
                "button.pair_stop",
            ]
            await page.evaluate("calls=[]")
            await card.locator(".compact-stop").click()
            await page.evaluate("card.updateComplete")
            assert await page.evaluate("calls.map(c=>c.entity_id)") == ["button.pair_stop"]
            await page.evaluate("hass=stopTestHass;card.hass=hass")

        # A late successful STOP cannot discard a newer movement on the same side.
        await page.evaluate("""async () => {
          window.stopTestHass=hass;
          hass={...hass,callService:(domain,service,data)=>{
            calls.push({domain,service,...data});
            if(data.entity_id==='button.left_stop') return new Promise(resolve=>{window.finishStop=resolve});
            return Promise.resolve();
          }};card.hass=hass;await configure();
        }""")
        await card.get_by_role("button", name="Left", exact=True).click()
        await card.locator(".compact-actions .tile").first.click()
        await card.locator(".compact-stop").click()
        await card.locator(".compact-actions .tile").first.click()
        await page.evaluate("async ()=>{finishStop();await card.updateComplete;}")
        await card.get_by_role("button", name="Right", exact=True).click()
        await page.evaluate("calls=[]")
        await card.locator(".compact-stop").click()
        assert await page.evaluate("calls.some(c=>c.entity_id==='button.left_stop')")
        await page.evaluate(
            "async ()=>{finishStop();await card.updateComplete;hass=stopTestHass;card.hass=hass;}"
        )

        # A preset-only target without an exposed STOP cannot start movement.
        await page.evaluate("""async () => {
          window.originalHass=hass;
          const entities={...hass.entities};delete entities['button.pair_stop'];
          hass={...hass,entities};card.hass=hass;await configure({default_target:'both'});
        }""")
        assert await card.locator(".compact-actions .tile").first.is_disabled()
        await page.evaluate("hass=originalHass;card.hass=hass")

        # A target change releases a pointer/keyboard hold on its original side.
        await page.evaluate("configure({show_motors:true})")
        await card.get_by_role("button", name="Left", exact=True).click()
        up = card.get_by_role("button", name="Up", exact=True).first
        await up.focus()
        await page.keyboard.down("Space")
        await card.get_by_role("button", name="Right", exact=True).click()
        await page.keyboard.up("Space")
        assert await page.evaluate(
            "calls.some(c=>c.entity_id==='cover.left_back' && c.service==='stop_cover')"
        )
        await page.evaluate("async ()=>{await Promise.resolve();await card.updateComplete;calls=[]}")
        await card.locator(".compact-stop").click()
        release_calls = await page.evaluate("calls.map(c=>c.entity_id)")
        assert release_calls == ["button.right_stop"], release_calls

        # Side-scoped assistive activation also remains stoppable after a tab change.
        await page.evaluate("calls=[]")
        await card.get_by_role("button", name="Up", exact=True).first.evaluate("el=>el.click()")
        await card.get_by_role("button", name="Left", exact=True).click()
        await card.locator(".compact-stop").click()
        assert await page.evaluate("calls.some(c=>c.entity_id==='button.right_stop')")

        # Explicitly invalid fixed target cannot silently act on a different side.
        await page.evaluate("configure({default_target:'removed',show_side_selector:false})")
        assert await card.locator(".compact-actions .tile").count() == 0
        assert "Choose an available" in await card.locator(".compact-card").inner_text()

        await page.evaluate(
            "configure({compact_actions:[],show_header:false,compact_labels:'none'})"
        )
        assert await card.locator(".compact-tabs").count() == 0
        assert await card.locator(".compact-actions").count() == 0
        assert await card.locator(".compact-header").count() == 0
        assert await card.locator(".dual-bed-side").count() == 2
        await card.locator(".compact-graphic").click()
        assert await page.evaluate("location.pathname") == "/dashboard/bed"

        # Unknown feedback is not rendered as flat; reduced motion is respected.
        await page.evaluate(
            """hass={...hass,states:{...hass.states,'number.left_back_position':{...hass.states['number.left_back_position'],state:'unknown'}}};card.hass=hass;"""
        )
        await card.locator(".compact-no-position").wait_for()
        assert await card.locator(".dual-bed-side").count() == 0
        await page.evaluate(
            """hass={...hass,states:{...hass.states,'number.left_back_position':{...hass.states['number.left_back_position'],state:'75'}}};card.hass=hass;"""
        )
        await card.locator(".dual-bed-side").first.wait_for()
        await page.emulate_media(reduced_motion="reduce")
        assert (
            await card.locator(".dual-bed-panel").first.evaluate(
                "el=>getComputedStyle(el).transitionDuration"
            )
            == "0s"
        )

        # Every recipe is available in the editor and applies explicit settings.
        await page.evaluate("""window.editor=document.createElement('adjustable-bed-card-editor');
          editor.hass=hass; editor.setConfig(base); document.body.append(editor);
          window.edited=base;editor.addEventListener('config-changed',e=>{edited=e.detail.config;editor.setConfig(edited);card.setConfig(edited)});""")
        editor = page.locator("adjustable-bed-card-editor")
        await editor.get_by_role("button", name="A · Glance only", exact=True).click()
        assert await page.evaluate("edited.compact_actions.length") == 0
        await editor.get_by_role("button", name="B · Quick actions", exact=True).click()
        assert await page.evaluate("edited.show_motors") is False
        assert await card.locator(".compact-actions .tile").count() == 3
        await editor.get_by_role("button", name="C · Compact controls", exact=True).click()
        assert await page.evaluate("edited.show_motors") is True
        assert await card.locator(".compact-motors").count() == 1
        # Full-card settings include memory available only on a side.
        await page.evaluate("""() => {
          const entity_id='button.left_program_memory_3';
          const sideHass={...hass, entities:{...hass.entities,[entity_id]:{entity_id,device_id:'left',platform:'adjustable_bed',translation_key:'program_memory_3'}}};
          editor.hass=sideHass;editor.setConfig({...base,layout:'full'});
        }""")
        assert "Memory 3" in await editor.locator(".sub").inner_text()
        # A stale target remains repairable after unpairing to a standalone bed.
        await page.evaluate("""async () => {
          editor.hass={...hass, devices:{left:{id:'left',name:'Single bed'}}};
          editor.setConfig({...base,device_id:'left',default_target:'removed'});
          await editor.updateComplete;
        }""")
        stale = editor.locator("label").filter(has_text="Default / fixed target").locator("select")
        await stale.select_option("both")
        assert await page.evaluate("edited.default_target") == "both"
        await editor.evaluate("el=>el.remove()")

        # The same compact renderer supports a one-address pair, including
        # normalized favourites, and standalone beds without a side selector.
        await page.evaluate("""async () => {window.nativeHass=hass;
          const entities={}, states={};
          for(const [id,entry] of Object.entries(hass.entities)) {
            const side=entry.device_id==='pair'?'both':entry.device_id;
            entities[id]={...entry,device_id:'pair',translation_key:entry.translation_key+'_'+side};
            states[id]={...hass.states[id],attributes:{...hass.states[id].attributes,bed_side:side}};
          }
          hass={...hass,devices:{pair:{id:'pair',name:'Bed'}},entities,states};card.hass=hass;
          await configure({default_target:'right'});}""")
        assert await card.locator(".dual-bed-side").count() == 2
        await card.locator(".compact-actions .tile").first.click()
        assert await page.evaluate("calls.at(-1).entity_id") == "button.right_preset_flat"
        await page.evaluate("""async () => {hass={...nativeHass,devices:{left:{id:'left',name:'Single bed'}}};
          card.hass=hass;await configure({device_id:'left'});}""")
        assert await card.locator(".compact-tabs").count() == 0
        assert await card.locator(".bed-graphic-theme").count() == 1
        await page.evaluate(
            "async () => {hass=nativeHass;card.hass=hass;await configure({show_motors:true})}"
        )

        for width in [180, 240, 320, 440]:
            await page.locator("main").evaluate("(el,width)=>el.style.width=width+'px'", width)
            assert await card.locator("ha-card").evaluate("el=>el.scrollWidth<=el.clientWidth+1"), (
                width
            )
        if output := os.environ.get("CARD_SCREENSHOT_DIR"):
            root = Path(output)
            root.mkdir(parents=True, exist_ok=True)
            await page.locator("main").evaluate("el=>el.style.width='320px'")
            await page.evaluate("hass.states['number.left_back_position'].state='38'")
            for preset, config in [
                ("a", {"compact_actions": [], "compact_labels": "names"}),
                ("b", {}),
                ("c", {"show_motors": True}),
            ]:
                await page.evaluate("configure", config)
                await card.screenshot(path=str(root / f"compact-{preset}.png"))
        assert not errors, errors
        await browser.close()
        print(
            "Compact browser checks passed: routing, hold cleanup, STOP ownership, editor recipes, navigation, feedback, motion, responsive sizing."
        )


asyncio.run(main())
