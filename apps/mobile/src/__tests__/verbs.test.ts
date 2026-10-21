import { pieces, verbOf } from "@/school/verbText";

const index = { habite: "habiter", ai: "avoir", est: "etre", parlons: "parler", went: "go", vont: "aller" };

describe("verbs a learner can tap", () => {
  it("finds the verb behind an elided pronoun and a capital", () => {
    expect(verbOf("J'habite", index)).toBe("habiter");
    expect(verbOf("j’ai", index)).toBe("avoir");
    expect(verbOf("Est-ce", index)).toBe("etre");
    expect(verbOf("maison", index)).toBeUndefined();
  });

  it("splits a line into highlights and verbs, keeping every character", () => {
    const line = "Nous **parlons** au port, et ils vont bien.";
    const out = pieces(line, index);
    expect(out.map((p) => p.text).join("")).toBe(line.replaceAll("**", ""));
    expect(out.find((p) => p.text === "parlons")).toEqual({ text: "parlons", strong: true, verb: "parler" });
    expect(out.find((p) => p.text === "vont")).toEqual({ text: "vont", verb: "aller" });
    expect(out.filter((p) => !p.verb && !p.strong).length).toBe(3);
  });

  it("shows highlights alone while the index loads", () => {
    expect(pieces("I **went** home.", null)).toEqual([{ text: "I " }, { text: "went", strong: true }, { text: " home." }]);
  });
});
