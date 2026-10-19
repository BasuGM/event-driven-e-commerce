import { describe, expect, it } from "vitest"

import { shippingDefaults } from "./checkout-form"

describe("shippingDefaults", () => {
  it("prefills the last order's address and keeps the account name", () => {
    const last = { full_name: "Old Name", street: "Av. Paulista, 1000", city: "São Paulo", state: "SP", zip_code: "01310100" }
    expect(shippingDefaults("Carla Costa", last)).toEqual({
      full_name: "Carla Costa",
      street: "Av. Paulista, 1000",
      city: "São Paulo",
      state: "SP",
      zip_code: "01310-100",
    })
  })

  it("leaves the address empty without a previous order", () => {
    expect(shippingDefaults("Carla Costa", null)).toEqual({
      full_name: "Carla Costa",
      street: "",
      city: "",
      state: undefined,
      zip_code: "",
    })
  })
})
