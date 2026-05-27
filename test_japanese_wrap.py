import unittest

import japanese_wrap as jw


class PreferredJapaneseBreakTests(unittest.TestCase):
    def test_prefers_break_after_nimo_with_rule_engine(self):
        prefix = "配送記録を確認すると、佐川急便側にも"
        text = prefix + "言い分はあるため、関係者へ状況を整理して共有しました。"
        wrapped = jw.wrap_japanese(text, target=jw.text_width(prefix), min_ratio=0.50, engine="rule")
        self.assertEqual(wrapped.splitlines()[0], prefix)

    def test_prefers_break_after_matawa_with_rule_engine(self):
        prefix = "利用者へ渡す備品として、こちら側にもスプーンまたは"
        text = prefix + "フォークを用意し、受け取り方法を案内しました。"
        wrapped = jw.wrap_japanese(text, target=jw.text_width(prefix), min_ratio=0.50, engine="rule")
        self.assertEqual(wrapped.splitlines()[0], prefix)

    def test_prefers_other_choice_and_listing_expressions(self):
        cases = [
            ("返金もしくは", "交換を案内します。"),
            ("メールあるいは", "電話で連絡します。"),
            ("取扱説明書および", "保証書を渡します。"),
            ("担当部署ならびに", "責任者へ共有します。"),
        ]
        for boundary, suffix in cases:
            with self.subTest(boundary=boundary):
                prefix = "必要な選択肢として" + boundary
                wrapped = jw.wrap_japanese(
                    prefix + suffix,
                    target=jw.text_width(prefix),
                    min_ratio=0.50,
                    engine="rule",
                )
                self.assertEqual(wrapped.splitlines()[0], prefix)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_prefers_requested_boundaries_with_sudachi(self):
        cases = [
            (
                "配送記録を確認すると、佐川急便側にも",
                "言い分はあるため、関係者へ状況を整理して共有しました。",
            ),
            (
                "利用者へ渡す備品として、こちら側にもスプーンまたは",
                "フォークを用意し、受け取り方法を案内しました。",
            ),
        ]
        for prefix, suffix in cases:
            with self.subTest(prefix=prefix):
                wrapped = jw.wrap_japanese(
                    prefix + suffix,
                    target=jw.text_width(prefix),
                    min_ratio=0.50,
                    engine="sudachi",
                )
                self.assertEqual(wrapped.splitlines()[0], prefix)


class AcademicDocumentTests(unittest.TestCase):
    def assert_token_is_not_split(self, wrapped, token):
        compact = wrapped.replace("\n", "")
        self.assertIn(token, compact)
        start = compact.index(token)
        boundaries = []
        offset = 0
        for line in wrapped.splitlines()[:-1]:
            offset += len(line)
            boundaries.append(offset)
        self.assertFalse(any(start < boundary < start + len(token) for boundary in boundaries))

    def test_reflow_joins_lines_inside_paragraph_but_keeps_blank_line(self):
        text = "第一段落は途中で\n抽出時に改行されています。\n\n第二段落は独立しています。"
        self.assertEqual(
            jw.reflow_paragraphs(text),
            ["第一段落は途中で抽出時に改行されています。", "", "第二段落は独立しています。"],
        )

    def test_reflow_preserves_space_at_extracted_line_boundary(self):
        text = "Japanese Technical Text.\n Journal of Layout"
        self.assertEqual(
            jw.reflow_paragraphs(text),
            ["Japanese Technical Text. Journal of Layout"],
        )

    def test_protects_academic_identifiers_and_units(self):
        tokens = [
            "https://example.org/papers?id=AB-12",
            "10.1234/ABC.2026.17",
            "author@example.org",
            "10.5mg",
            "JP-2026-A17",
            "v3.4.1",
            "(Tanaka, 2024)",
            "（Tanaka, 2024）",
        ]
        text = "結果は" + "、".join(tokens) + "に記録され、再確認の対象となりました。"
        wrapped = jw.wrap_japanese(text, target=54, min_ratio=0.40, engine="rule")
        for token in tokens:
            with self.subTest(token=token):
                self.assert_token_is_not_split(wrapped, token)

    def test_text_within_target_is_not_rewrapped(self):
        text = "佐川急便側にも言い分はある。"
        self.assertEqual(jw.wrap_japanese(text, target=86, engine="rule"), text)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_cost_strategy_selects_semantic_boundaries_directly(self):
        cases = [
            (
                "戻したあと、「眠れない深夜に決めたことを、温室跡の外で簡単に言い換えないで"
                "ください」と付け加えた。温室跡で確かめた事実は小さくても、寄贈の理由を知る助けになる。",
                "ください」と",
            ),
            (
                "不自然に整然としていた。遠い足音の合間に修復師の白井は「寄贈の理由を"
                "知るために、眠れない深夜の発言を一語ずつ確かめさせてください」と言った。温室跡の",
                "知るために、",
            ),
            (
                "机上灯の円に照らされた収蔵庫で、司書の環は洪水の晩をたどるための一覧を作った。"
                "項目には欠けた標本札、時刻、受領者、確認方法が並び、確認できない欄には細い付箋を"
                "置いた。遠い足音の合間に修復師の白井は「持ち主の名を確かめるために、"
                "雨の夕方の発言を一語ずつ確かめさせてください」と言った。資料閲覧室で確認できない欄は、"
                "寄贈の理由を知るまで未確認のまま残すと決めた。",
                "雨の",
            ),
            (
                "閉館直前が過ぎても、海辺の標本館には低いモーター音が残った。司書の環は"
                "銀色の鍵の番号を読み上げ、修復師の白井は資料閲覧室の一覧に印を付けた。過去との照合を",
                "銀色の鍵の番号を",
            ),
        ]
        for text, first_line_ending in cases:
            with self.subTest(first_line_ending=first_line_ending):
                lines = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="cost").splitlines()
                self.assertTrue(any(line.endswith(first_line_ending) for line in lines), lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_cost_strategy_does_not_leave_adverb_before_its_verb(self):
        text = (
            "遠い足音の合間に修復師の白井は「持ち主の名を確かめるために、雨の夕方の発言を"
            "一語ずつ確かめさせてください」と言った。資料閲覧室で確認できない欄は、"
        )
        wrapped = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="cost")
        self.assertNotIn("一語ずつ\n確かめ", wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_keeps_reviewed_narrative_phrases_together(self):
        cases = [
            (
                "雲の切れ間から薄い陽が落ち、旧堤防の観測小屋は訪れる者へ何かを"
                "ためらっているようだった。一度は閉じた資料をもう一度開き、美緒は観測ノートと役所の",
                "ためらっている",
            ),
            (
                "白井が封筒を伏せて置いたのを見て、彼女は「帰路につく前まで待てば、収蔵庫で"
                "話せることがもう少し増えます」という発言を引用符のまま保存した。温室跡で確かめた事実は",
                "話せることが",
            ),
            (
                "戻したあと、「眠れない深夜に決めたことを、温室跡の外で簡単に言い換えないで"
                "ください」と付け加えた。温室跡で確かめた事実は小さくても、寄贈の理由を知る助けになる。",
                "ください」と",
            ),
            (
                "不自然に整然としていた。遠い足音の合間に修復師の白井は「寄贈の理由を"
                "知るために、眠れない深夜の発言を一語ずつ確かめさせてください」と言った。温室跡の",
                "知るために、",
            ),
            (
                "机上灯の円に照らされた収蔵庫で、司書の環は洪水の晩をたどるための一覧を作った。"
                "項目には欠けた標本札、時刻、受領者、確認方法が並び、確認できない欄には細い付箋を"
                "置いた。遠い足音の合間に修復師の白井は「持ち主の名を確かめるために、"
                "雨の夕方の発言を一語ずつ確かめさせてください」と言った。資料閲覧室で確認できない欄は、",
                "雨の夕方の発言を",
            ),
            (
                "閉館直前が過ぎても、海辺の標本館には低いモーター音が残った。司書の環は"
                "銀色の鍵の番号を読み上げ、修復師の白井は資料閲覧室の一覧に印を付けた。過去との照合を",
                "銀色の鍵の番号を",
            ),
        ]
        for text, ending in cases:
            with self.subTest(ending=ending):
                lines = jw.wrap_japanese(
                    text,
                    target=86,
                    engine="sudachi",
                    strategy="global-cost",
                ).splitlines()
                self.assertTrue(any(line.endswith(ending) for line in lines), lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_does_not_open_a_break_inside_a_verb(self):
        text = (
            "付箋を置いた。遠い足音の合間に修復師の白井は「持ち主の名を確かめるために、"
            "雨の夕方の発言を一語ずつ確かめさせてください」と言った。資料閲覧室で確認できない欄は、"
        )
        wrapped = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="global-cost")
        self.assertNotIn("確か\nめ", wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_keeps_identifier_with_its_label_when_space_allows(self):
        text = (
            "「メールまたは電話のどちらでも構いません」と受付の人は言った。「ただ、受付番号"
            "TK-2098を伝えてください。そうしないと、記録を確認できないことがあります。」"
            "声は丁寧だったが、背後では誰かが慌ただしく資料をめくっていた。"
        )
        wrapped = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="global-cost")
        self.assertNotIn("受付番号\nTK-2098", wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_genitive_split_for_balance(self):
        text = (
            "海辺の標本館では、低いモーター音だけが普段と変わらず続いていた。司書の環が押し花の"
            "封筒を開かずに調べると、手がかりの発見を示す小さな違いがあった。修復師の白井は椅子を"
            "引き寄せたあと、「昼過ぎに聞いた話と、温室跡に残る記録は同じではありません」と"
            "付け加えた。静かな継承を語るほど、潮で波打った台帳を手渡せなかった事情が重くなる。"
        )
        wrapped = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="global-cost")
        self.assertLessEqual(
            jw.semantic_break_cost("押し花の封筒", len("押し花の"), None),
            20,
        )
        self.assertIn("押し花の\n封筒", wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_identifier_label_before_number_reading(self):
        text = (
            "眠れない深夜が過ぎても、山間の診療所には水の滴る音が残った。医師の志穂は"
            "薬瓶の空箱の番号を読み上げ、薬剤師の蓮は峠道の一覧に印を付けた。危機の予兆を確かめる"
            "途中で、彼は「家族へ知らせるために、夜明け前の発言を一語ずつ確かめさせてください」と"
            "言った。患者の約束を守ることを急ぐほど、編まれた膝掛けを急いで解釈すれば、"
            "雪置き場で聞いた声を消してしまう。"
        )
        lines = jw.wrap_japanese(
            text,
            target=86,
            engine="sudachi",
            strategy="global-cost",
        ).splitlines()
        self.assertTrue(any(line.endswith("薬瓶の空箱の") for line in lines), lines)
        self.assertTrue(any(line.startswith("番号を読み上げ、") for line in lines), lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_reviewed_expired_modifier_boundary(self):
        text = (
            "朝の点検時刻が過ぎても、夜の環状線には不意の警報音が残った。車掌の深町は"
            "期限切れの定期券の番号を読み上げ、終電に乗る絵里は高架下の一覧に印を付けた。"
            "引返せない決断を確かめる途中で、彼は運行記録をもう一度開き、"
            "失われた時刻の手掛かりを探した。"
        )
        lines = jw.wrap_japanese(
            text,
            target=86,
            engine="sudachi",
            strategy="global-cost",
        ).splitlines()
        self.assertLessEqual(
            jw.semantic_break_cost("期限切れの定期券", len("期限切れの"), None),
            20,
        )
        self.assertTrue(any(line.endswith("期限切れの") for line in lines), lines)
        self.assertTrue(any(line.startswith("定期券の番号を読み上げ、") for line in lines), lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_short_personal_genitive_boundary(self):
        text = (
            "朝の点検時刻が過ぎても、診療所には不意のベルの音が残った。看護師の志穂は"
            "僕の首の皺の深さを読み上げず、封筒に残った宛名をそっと読み返した。"
            "言えなかった事情を確かめる途中で、彼女は記録をもう一度開いた。"
        )
        wrapped = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="global-cost")
        self.assertLessEqual(
            jw.semantic_break_cost("僕の首の皺の深さ", len("僕の首の皺の"), None),
            20,
        )
        self.assertTrue(all(jw.text_width(line) <= 86 for line in wrapped.splitlines()))

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_conditional_genitive_boundary(self):
        text = (
            "障害報告には、エラーが含まれていた場合の異常終了や、認証情報が欠落していた場合の"
            "警告の内容が並び、担当者は発生条件と再試行の可否を一項目ずつ確認した。"
        )
        wrapped = jw.wrap_japanese(text, target=42, engine="sudachi", strategy="global-cost")
        self.assertLessEqual(
            jw.semantic_break_cost(
                "エラーが含まれていた場合の異常終了",
                len("エラーが含まれていた場合の"),
                None,
            ),
            20,
        )
        self.assertIn("場合の\n", wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_is_the_default_strategy(self):
        text = (
            "報告書には、エラーが含まれていた場合の異常終了や、認証情報が欠落していた場合の"
            "警告の内容が並び、担当者は再試行の可否を確認した。"
        )
        self.assertEqual(
            jw.wrap_japanese(text, target=42, engine="sudachi"),
            jw.wrap_japanese(text, target=42, engine="sudachi", strategy="global-cost"),
        )

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_comma_before_adverbial_yagate(self):
        cases = [
            ("鉛筆を", "持ち替えて、"),
            ("椅子を", "引き寄せて、"),
        ]
        for object_phrase, moved in cases:
            with self.subTest(moved=moved):
                text = (
                    "子どもの笑い声を聞いた音響係の莉子は、編集室で立ち止まった。手にある予備電池は"
                    f"軽いのに、その由来を説明する言葉は重かった。老アナウンサーの梶が{object_phrase}"
                    f"{moved}やがて「原稿の改変を知るまでは、放送台本を見た人の名前を伏せてください」と"
                    "告げた。雨の夕方までに原稿の改変を知るには、共同作業の始まりを避けて通れなかった。"
                )
                lines = jw.wrap_japanese(
                    text,
                    target=86,
                    engine="sudachi",
                    strategy="global-cost",
                ).splitlines()
                self.assertTrue(any(line.endswith(moved) for line in lines), lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_does_not_push_a_gap_into_the_next_pair(self):
        text = (
            "朝市へ向かう途中、調律師の紬は漁師の秋生から演奏会記録の由来を聞いた。「昼過ぎまで"
            "待てば、舞台袖で話せることがもう少し増えます」。一致を示す日付は一つも"
            "確かめられなかった。昼過ぎの非常灯の赤みを頼りに、二人は演奏者を捜す順序を決め直した。"
        )
        lines = jw.wrap_japanese(
            text,
            target=86,
            engine="sudachi",
            strategy="global-cost",
        ).splitlines()
        gaps = [
            jw.text_width(following) - jw.text_width(current)
            for current, following in zip(lines, lines[1:])
        ]
        self.assertLessEqual(max(gaps), 12, lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_moves_sentence_completion_when_neighbor_balance_improves(self):
        text = (
            "新聞社の窓には月の青白さが映り、仕立師の小春の手元の帳場帳も同じ色に染まった。"
            "危機の予兆をめぐる話は互いに食い違っていたが、新聞記者の壮介の「雨の夕方に"
            "決めたことを、新聞社の外で簡単に言い換えないでください」という一文だけは"
            "一致していた。鉛筆を持ち替えた彼女は、新聞社の記憶は、縫込みの紙片一つの所有者だけに"
            "委ねられるものではないと理解し、縫い込まれた名を読む準備を続けた。"
        )
        lines = jw.wrap_japanese(
            text,
            target=86,
            engine="sudachi",
            strategy="global-cost",
        ).splitlines()
        self.assertTrue(any(line.endswith("一致していた。") for line in lines), lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_can_complete_phrase_after_genitive_boundaries_are_allowed(self):
        text = (
            "雨の夕方、測量士の悠真は堤防で補償一覧を見つけた。机上灯の円の下では、"
            "水染みの輪郭だけが日付より正確に残っていた。商店主の圭子は「住民の声を"
            "集めるまでは、赤い測量杭を見た人の名前を伏せてください」と言い、椅子を引き寄せた。"
            "消えた道を探すためには、過去との照合を曖昧なままにできないと彼女は考えた。"
        )
        lines = jw.wrap_japanese(
            text,
            target=86,
            engine="sudachi",
            strategy="global-cost",
        ).splitlines()
        self.assertTrue(any(line.endswith("集めるまでは、") for line in lines), lines)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_closes_quoted_request_before_reporting_clause(self):
        text = (
            "閉館直前が過ぎても、高原の旧天文台には子どもの笑い声が残った。大学院生の玲は"
            "観測ノートの番号を読み上げ、高校生の紗良は雪原の一覧に印を付けた。過去との照合を"
            "確かめる途中で、彼は「観測ドームへ戻るなら、流星写真の傷を先に写真に"
            "残してください」と言った。未発表の発見を検証することを急ぐほど、麓の駅の記憶は、"
            "流星写真一つの所有者だけに委ねられるものではない。"
        )
        lines = jw.wrap_japanese(
            text,
            target=86,
            engine="sudachi",
            strategy="global-cost",
        ).splitlines()
        self.assertIn("残してください」と言った。", "\n".join(lines))
        self.assertNotIn("」と\n言った", "\n".join(lines))

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_reflows_residual_gaps_without_splitting_phrases(self):
        cases = [
            (
                "窓から差す薄明かりに照らされた車内最後部で、車掌の深町は消えた停車時刻を"
                "調べるための一覧を作った。項目には録音機、所在、状態、閲覧の条件が並び、"
                "空欄の意味を決めるには証言が不足していた。時計の小さな刻みの合間に"
                "終電に乗る絵里は「高架下へ戻るなら、拾得物の手帳の傷を先に写真に"
                "残してください」と言った。青い手袋の空欄を想像で埋めないことが、"
                "引返せない決断への最初の約束になった。",
                "調べるための\n一覧",
                True,
            ),
            (
                "朝の点検時刻が過ぎても、夜の環状線には子どもの笑い声が残った。車掌の深町は"
                "青い手袋の番号を読み上げ、終電に乗る絵里は無人改札の一覧に印を付けた。"
                "誤解の解消を確かめる途中で、彼は「青い手袋だけを読んでも、"
                "乗客の伝言を渡す理由には届かないでしょう」と言った。消えた停車時刻を"
                "調べることを急ぐほど、無人改札の記憶は、拾得物の手帳一つの所有者だけに"
                "委ねられるものではない。",
                "誤解の解消を\n確かめる",
                False,
            ),
        ]
        for text, boundary, expected in cases:
            with self.subTest(boundary=boundary):
                wrapped = jw.wrap_japanese(
                    text,
                    target=86,
                    engine="sudachi",
                    strategy="global-cost",
                )
                lines = wrapped.splitlines()
                later_gaps = [
                    jw.text_width(following) - jw.text_width(current)
                    for current, following in zip(lines, lines[1:])
                ]
                self.assertLess(max(later_gaps), 12, lines)
                if expected:
                    self.assertIn(boundary, wrapped)
                else:
                    self.assertNotIn(boundary, wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_observed_artifact_property_boundary(self):
        text = (
            "帰路につく前、医師の志穂は薬剤師の蓮と待合室に戻った。昨日は見落とした"
            "薬瓶の空箱の傷が、夕暮れの反射によって浮かび上がったからである。息を飲んだ彼女は、"
            "家族へ知らせるには引返せない決断の経緯まで記す必要があると悟った。"
            "「薬瓶の空箱は忘れ物ではなく、峠道へ戻れなかった人の印です」という声が、"
            "水の滴る音に紛れず残った。"
        )
        wrapped = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="global-cost")
        self.assertLessEqual(
            jw.semantic_break_cost("薬瓶の空箱の傷", len("薬瓶の空箱の"), None),
            20,
        )

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_allows_purpose_phrase_before_list_noun(self):
        cases = [
            (
                "窓から差す薄明かりに照らされた無人改札で、車掌の深町は消えた停車時刻を"
                "調べるための一覧を作った。項目には期限切れの定期券、損傷箇所、封印の有無、"
                "確認日が並び、未記入の箇所だけが不自然に整然としていた。紙の擦れる音の合間に"
                "終電に乗る絵里は「帰路につく前に決めたことを、折返し線の外で簡単に"
                "言い換えないでください」と言った。帰れなかった理由を聞く前に、青い手袋の記載と"
                "車内最後部での聞取りを別々に保管した。",
                "調べるための",
            ),
            (
                "白い蛍光灯に照らされた第三区画スタジオで、音響係の莉子は届かなかった声を"
                "探すための一覧を作った。項目には放送台本、時刻、受領者、確認方法が並び、"
                "確認できない欄には細い付箋を置いた。時計の小さな刻みの合間に"
                "老アナウンサーの梶は「放送台本は忘れ物ではなく、避難所へ戻れなかった人の印です」と"
                "言った。ノイズの録音の空欄を想像で埋めないことが、共同作業の始まりへの"
                "最初の約束になった。",
                "探すための",
            ),
        ]
        for text, prefix in cases:
            with self.subTest(prefix=prefix):
                lines = jw.wrap_japanese(
                    text,
                    target=86,
                    engine="sudachi",
                    strategy="global-cost",
                ).splitlines()
                self.assertTrue(any(line.endswith(prefix) for line in lines), lines)
                self.assertTrue(any(line.startswith("一覧を") for line in lines), lines)
                self.assertNotIn("では\nなく", "\n".join(lines))

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_keeps_negative_predicate_together(self):
        texts = [
            (
                "地方ラジオ局を出る直前、音響係の莉子は受信報告葉書を元の位置へ戻した。"
                "老アナウンサーの梶が「風の止んだ朝に聞いた話と、第三区画スタジオに残る記録は"
                "同じではありません」と話した以上、届かなかった声を探す作業は一人の確信だけで"
                "進められない。編集室の雨ににじむ街灯を消す前に、彼女は手がかりの発見と"
                "第三区画スタジオへ帰る道は、次の警報を届ける結論より先に守られなければならない"
                "という二つの文を別々に記録した。"
            ),
            (
                "航行する農業船では、不意の警報音だけが普段と変わらず続いていた。植物技師のナナが"
                "発芽ケースを開かずに調べると、手がかりの発見を示す小さな違いがあった。"
                "航法士のユルはノートの頁を戻したあと、「夜明け前に聞いた話と、水耕室に残る記録は"
                "同じではありません」と付け加えた。発芽ケースに残る空白も、"
                "証言の食違いを知るための記録になる。"
            ),
        ]
        for text in texts:
            with self.subTest(text=text):
                wrapped = jw.wrap_japanese(text, target=86, engine="sudachi", strategy="global-cost")
                self.assertNotIn("では\nなく", wrapped)
                self.assertNotIn("では\nありません", wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_global_cost_preserves_readable_action_clause_after_genitive_reflow(self):
        cases = [
            (
                "海辺の標本館では、水の滴る音だけが普段と変わらず続いていた。司書の環が"
                "押し花の封筒を開かずに調べると、静かな継承を示す小さな違いがあった。"
                "修復師の白井は椅子を引き寄せたあと、「押し花の封筒の空欄を埋める前に、"
                "温室跡で聞いた声を残してください」と付け加えた。静かな継承を語るほど、"
                "押し花の封筒を手渡せなかった事情が重くなる。",
                "椅子を引き寄せた",
            ),
            (
                "山間の診療所では、水の滴る音だけが普段と変わらず続いていた。医師の志穂が"
                "薬瓶の空箱を開かずに調べると、過去との照合を示す小さな違いがあった。"
                "薬剤師の蓮は鉛筆を持ち替えたあと、「青い問診票を処置室から動かすなら、"
                "受け取った時刻も記してください」と付け加えた。編まれた膝掛けに残る空白も、"
                "静かな継承を知るための記録になる。",
                "鉛筆を持ち替えた",
            ),
        ]
        for text, ending in cases:
            with self.subTest(ending=ending):
                lines = jw.wrap_japanese(
                    text,
                    target=86,
                    engine="sudachi",
                    strategy="global-cost",
                ).splitlines()
                wrapped = "\n".join(lines)
                verb = ending.split("を", 1)[1]
                self.assertIn(f"{verb}あと、「", wrapped)
                self.assertNotIn("では\nなく", wrapped)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_reduces_large_first_to_second_line_imbalance(self):
        text = (
            "段落0004。実験条件には濃度5.2%および投与量10.5mgに関する記述を含めた。"
            "選択肢として返金もしくは交換を提示する場合、接続表現の後ろが読みやすい"
            "切れ目となる。一方で、見出しや参考文献を本文と区別する処理については"
            "今後の検討課題である。"
        )
        lines = jw.wrap_japanese(text, target=86, engine="sudachi").splitlines()
        widths = [jw.text_width(line) for line in lines]
        self.assertLess(widths[1] - widths[0], 16)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_balances_public_academic_abstract_at_natural_punctuation_break(self):
        text = (
            "日本では三時間積算降水量二百ミリメートルを超える集中豪雨がしばしば"
            "観測され、深刻な地滑りや洪水をもたらす。そのような事例は主に、"
            "日本語で線状降水帯と名付けられた準停滞線状降水システムによってもたらされる。"
        )
        lines = jw.wrap_japanese(text, target=86, engine="sudachi").splitlines()
        widths = [jw.text_width(line) for line in lines]
        self.assertEqual(lines[0][-5:], "観測され、")
        self.assertLess(widths[1] - widths[0], 16)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_moves_readable_prefixes_forward_to_balance_narrative_lines(self):
        cases = [
            (
                "雲の切れ間から薄い陽が落ち、旧堤防の観測小屋は訪れる者へ何かを",
                "ためらっているようだった。一度は閉じた資料をもう一度開き、美緒は観測ノートと役所の",
                "ためらっている",
            ),
            (
                "離島航路の客船へ着いたとき、エンジンの震えが椅子へ伝わり、聞き取りを",
                "始めるには少し早く、観察するには十分な静けさがあった。窓際で編み物をする女性から",
                "始めるには",
            ),
            (
                "持ってきた帳面と値が一致します」と告げられた。その声を断定の根拠にはせず、",
                "新しい照合先を見つけた印として扱った。美緒は欠測の理由を推定と呼んでよいのかを考えた。",
                "新しい",
            ),
            (
                "答えは「その箱は今朝までなかったはずです」という短いものだった。すぐ返事を",
                "求めないほうが続きが聞けると考え、美緒は静かに頷いた。念のため、折り込まれた紙面には、",
                "求めない",
            ),
            (
                "夕暮れの反射に照らされた温室跡で、司書の環は寄贈の理由を知るための一覧を",
                "作った。項目には潮で波打った台帳、損傷箇所、封印の有無、確認日が並び、埋まらない一欄が",
                "作った。",
            ),
            (
                "白井が封筒を伏せて置いたのを見て、彼女は「帰路につく前まで待てば、収蔵庫で",
                "話せることがもう少し増えます」という発言を引用符のまま保存した。温室跡で確かめた事実は",
                "話せることが",
            ),
            (
                "眠れない深夜が過ぎても、海辺の標本館には低いモーター音が残った。司書の",
                "環は銀色の鍵の番号を読み上げ、修復師の白井は温室跡の一覧に印を付けた。静かな継承を",
                "環は",
            ),
            (
                "波打った台帳の番号を読み上げ、修復師の白井は防潮扉の前の一覧に印を付けた。",
                "危機の予兆を確かめる途中で、彼は「欠けた標本札だけを読んでも、寄贈の理由を知る理由には",
                "危機の予兆を",
            ),
            (
                "戻したあと、「眠れない深夜に決めたことを、温室跡の外で簡単に言い換えないで",
                "ください」と付け加えた。温室跡で確かめた事実は小さくても、寄贈の理由を知る助けになる。",
                "ください」と",
            ),
            (
                "不自然に整然としていた。遠い足音の合間に修復師の白井は「寄贈の理由を",
                "知るために、眠れない深夜の発言を一語ずつ確かめさせてください」と言った。温室跡の",
                "知るために、",
            ),
            (
                "付箋を置いた。遠い足音の合間に修復師の白井は「持ち主の名を確かめるために、",
                "雨の夕方の発言を一語ずつ確かめさせてください」と言った。資料閲覧室で確認できない欄は、",
                "雨の夕方の",
            ),
            (
                "閉館直前が過ぎても、海辺の標本館には低いモーター音が残った。司書の環は",
                "銀色の鍵の番号を読み上げ、修復師の白井は資料閲覧室の一覧に印を付けた。過去との照合を",
                "銀色の鍵の番号を",
            ),
        ]
        minimum = 74
        for current, following, moved in cases:
            with self.subTest(moved=moved):
                polished = jw.polish_lines(
                    [current, following, "次の行には確認事項を記しておく。"],
                    86,
                    minimum,
                    "sudachi",
                    "C",
                )
                self.assertTrue(polished[0].endswith(moved), polished[0])

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_pushes_natural_suffix_into_following_line_when_middle_line_is_long(self):
        lines = [
            "答えは「その箱は今朝までなかったはずです」という短いものだった。声に迷いが",
            "混じったことは記憶にとどめ、記録には引用した言葉だけを残した。それでも、点検表は電源、",
            "照明、通信、通路の順に並び、最後の確認欄だけが鉛筆のまま残っていた。",
        ]
        polished = jw.polish_lines(lines, 86, 74, "sudachi", "C")
        widths = [jw.text_width(line) for line in polished]
        self.assertLess(
            max(abs(widths[1] - widths[0]), abs(widths[2] - widths[1])),
            max(
                abs(jw.text_width(lines[1]) - jw.text_width(lines[0])),
                abs(jw.text_width(lines[2]) - jw.text_width(lines[1])),
            ),
        )
        self.assertTrue(polished[1].endswith("点検表は"))
        self.assertTrue(polished[2].startswith("電源、"))

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_repairs_short_genitive_boundary_after_neighboring_balance_moves(self):
        cases = [
            [
                "眠れない深夜が過ぎても、海辺の標本館には低いモーター音が残った。司書の",
                "環は銀色の鍵の番号を読み上げ、修復師の白井は温室跡の一覧に印を付けた。静かな継承を",
                "確かめる途中で、彼は「銀色の鍵は忘れ物ではなく、防潮扉の前へ戻れなかった",
            ],
            [
                "帰路につく前が過ぎても、海辺の標本館には遠い足音が残った。司書の環は潮で",
                "波打った台帳の番号を読み上げ、修復師の白井は防潮扉の前の一覧に印を付けた。危機の",
                "予兆を確かめる途中で、彼は「欠けた標本札だけを読んでも、寄贈の理由を知る理由には",
            ],
        ]
        for lines in cases:
            with self.subTest(lines=lines):
                polished = jw.polish_lines(lines, 86, 74, "sudachi", "C")
                self.assertFalse(any(line.endswith(("司書の", "危機の")) for line in polished[:-1]), polished)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_repairs_title_split_before_katakana_name(self):
        lines = [
            "地方ラジオ局を出る直前、音響係の莉子は放送台本を元の位置へ戻した。老",
            "アナウンサーの梶が「風の止んだ朝まで待てば、避難所で話せることがもう少し増えます」と",
            "告げたので、机の上の記録を確認した。",
        ]
        polished = jw.polish_lines(lines, 86, 74, "sudachi", "C")
        wrapped = "\n".join(polished)
        self.assertNotIn("老\nアナウンサー", wrapped, polished)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_keeps_district_studio_name_together(self):
        lines = [
            "不自然に整然としていた。扉の軋みの合間に老アナウンサーの梶は「第三区",
            "画スタジオへ戻るなら、予備電池の傷を先に写真に残してください」と言った。過去との",
            "照合に向き合った記録だけが残った。",
        ]
        polished = jw.polish_lines(lines, 86, 74, "sudachi", "C")
        wrapped = "\n".join(polished)
        self.assertIn("第三区画スタジオ", wrapped.replace("\n", ""), polished)
        self.assertNotIn("第三区\n画", wrapped, polished)
        self.assertNotIn("第三区画\nスタジオ", wrapped, polished)

    @unittest.skipIf(jw.dictionary is None, "SudachiPy is not installed")
    def test_moves_short_sentence_completion_when_gap_is_extreme(self):
        lines = [
            "閉校予定の分校では、時計の小さな刻みだけが普段と変わらず",
            "続いていた。教師の知佳が気象観察表を開かずに調べると、証言の食違いを示す小さな",
            "違いがあり、記録に印を付けた。",
        ]
        polished = jw.polish_lines(lines, 86, 74, "sudachi", "C")
        self.assertTrue(polished[0].endswith("続いていた。"), polished)

if __name__ == "__main__":
    unittest.main()
