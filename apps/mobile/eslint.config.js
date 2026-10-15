// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", "src/contracts/generated.ts"],
  },
  {
    rules: {
      // i18next is used through its default instance (`i18n.use(...).init(...)`), as its docs do.
      "import/no-named-as-default-member": "off",
    },
  },
  {
    // jest.mock factories are hoisted above imports, so they must load modules with require().
    files: ["src/__tests__/**"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
]);
