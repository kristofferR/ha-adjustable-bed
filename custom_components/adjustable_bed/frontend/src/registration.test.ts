import { describe, expect, test } from "bun:test";
import {
  type CustomCardsWindow,
  type ElementRegistryWindow,
  defineElement,
  registerCustomCard,
} from "./registration";
import type { HomeAssistant } from "./types";

function hassWithEntity(
  platform: string,
  deviceId: string | undefined,
): HomeAssistant {
  return {
    entities: {
      "cover.bed_back": {
        entity_id: "cover.bed_back",
        device_id: deviceId,
        platform,
      },
    },
    states: {},
    devices: {},
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: async () => undefined,
  };
}

describe("custom card registration", () => {
  test("registers picker metadata once", () => {
    const target: CustomCardsWindow = {};

    registerCustomCard(target);
    registerCustomCard(target);

    expect(target.customCards).toHaveLength(1);
    expect(target.customCards?.[0]).toMatchObject({
      type: "adjustable-bed-card",
      name: "Adjustable Bed Card",
      preview: true,
    });
  });

  test("replaces stale metadata from an older bundle", () => {
    const target: CustomCardsWindow = {
      customCards: [
        {
          type: "adjustable-bed-card",
          name: "Old card metadata",
          description: "Old description",
        },
      ],
    };

    registerCustomCard(target);

    expect(target.customCards).toHaveLength(1);
    expect(target.customCards?.[0].name).toBe("Adjustable Bed Card");
    expect(target.customCards?.[0].getEntitySuggestion).toBeFunction();
  });

  test("suggests the card for Adjustable Bed entities", () => {
    const target: CustomCardsWindow = {};
    registerCustomCard(target);

    const suggestion = target.customCards?.[0].getEntitySuggestion?.(
      hassWithEntity("adjustable_bed", "bed-device"),
      "cover.bed_back",
    );

    expect(suggestion).toEqual({
      config: {
        type: "custom:adjustable-bed-card",
        device_id: "bed-device",
      },
    });
  });

  test("does not suggest the card for unrelated or device-less entities", () => {
    const target: CustomCardsWindow = {};
    registerCustomCard(target);
    const suggest = target.customCards?.[0].getEntitySuggestion;

    expect(
      suggest?.(hassWithEntity("light", "bed-device"), "cover.bed_back"),
    ).toBeNull();
    expect(
      suggest?.(
        hassWithEntity("adjustable_bed", undefined),
        "cover.bed_back",
      ),
    ).toBeNull();
  });
});

class FakeRegistry {
  private readonly elements = new Map<string, CustomElementConstructor>();
  private readonly waiters = new Map<
    string,
    (element: CustomElementConstructor) => void
  >();

  define(tag: string, element: CustomElementConstructor): void {
    if (this.elements.has(tag)) throw new Error(`${tag} already defined`);
    this.elements.set(tag, element);
    this.waiters.get(tag)?.(element);
  }

  get(tag: string): CustomElementConstructor | undefined {
    return this.elements.get(tag);
  }

  whenDefined(tag: string): Promise<CustomElementConstructor> {
    const element = this.elements.get(tag);
    if (element) return Promise.resolve(element);
    return new Promise((resolve) => this.waiters.set(tag, resolve));
  }
}

const CardElement = class {} as unknown as CustomElementConstructor;
const AppElement = class {} as unknown as CustomElementConstructor;
const flush = () => new Promise((resolve) => setTimeout(resolve));

describe("element definition", () => {
  test("survives the frontend replacing the registry after definition", async () => {
    const native = new FakeRegistry();
    const target: ElementRegistryWindow = { customElements: native };

    defineElement("adjustable-bed-card", CardElement, target);
    expect(native.get("adjustable-bed-card")).toBe(CardElement);

    // The polyfill installs a new registry, then defines <home-assistant>
    // through it, which also defines a stand-in natively.
    const scoped = new FakeRegistry();
    target.customElements = scoped;
    scoped.define("home-assistant", AppElement);
    native.define("home-assistant", AppElement);
    await flush();

    expect(scoped.get("adjustable-bed-card")).toBe(CardElement);
  });

  test("defines once when the frontend registry is already in place", async () => {
    const registry = new FakeRegistry();
    registry.define("home-assistant", AppElement);

    defineElement("adjustable-bed-card", CardElement, {
      customElements: registry,
    });
    await flush();

    expect(registry.get("adjustable-bed-card")).toBe(CardElement);
  });

  test("keeps a definition from an earlier bundle copy", async () => {
    const OlderCard = class {} as unknown as CustomElementConstructor;
    const registry = new FakeRegistry();
    registry.define("adjustable-bed-card", OlderCard);

    defineElement("adjustable-bed-card", CardElement, {
      customElements: registry,
    });
    registry.define("home-assistant", AppElement);
    await flush();

    expect(registry.get("adjustable-bed-card")).toBe(OlderCard);
  });
});
