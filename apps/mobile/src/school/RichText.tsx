/** A line of teaching: the parts to look at highlighted, and its verbs underlined so a tap opens their tables. In an
 * explanation only the highlighted words link (so « est » and « a » in every sentence don't); in examples, every verb. */
import * as Haptics from "expo-haptics";
import { Text, type StyleProp, type TextStyle } from "react-native";

import { useVerbLinks } from "@/school/verbs";
import { pieces } from "@/school/verbText";
import { colors, fonts } from "@/ui/theme";

export function RichText({
  text,
  style,
  numberOfLines,
  links = "all",
}: {
  text: string;
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
  links?: "all" | "highlighted";
}) {
  const { index, open } = useVerbLinks();
  return (
    <Text style={style} numberOfLines={numberOfLines}>
      {pieces(text, index).map((piece, i) => {
        const look = piece.strong ? strong : undefined;
        if (!piece.verb || (links === "highlighted" && !piece.strong)) {
          return (
            <Text key={i} style={look}>
              {piece.text}
            </Text>
          );
        }
        const verb = piece.verb;
        return (
          <Text
            key={i}
            accessibilityRole="link"
            accessibilityHint={verb}
            suppressHighlighting={false}
            onPress={() => {
              void Haptics.selectionAsync();
              open(verb);
            }}
            style={[look, linked]}
          >
            {piece.text}
          </Text>
        );
      })}
    </Text>
  );
}

const strong: TextStyle = { fontFamily: fonts.semibold, color: colors.accentDeep, backgroundColor: colors.accentSoft };
const linked: TextStyle = {
  textDecorationLine: "underline",
  textDecorationStyle: "dotted",
  textDecorationColor: colors.accent,
};
