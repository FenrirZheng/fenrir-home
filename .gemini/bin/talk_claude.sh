#!/bin/bash
MARKER="CHK-$RANDOM-$(date +%s)"
MY_PANE=$(bash ~/.gemini/skills/tmux-talk/scripts/talk here | awk '/pane_id:/ {print $2}')
bash ~/.gemini/skills/tmux-talk/scripts/talk send %1 "$(cat <<TALKMSG_EOF
嗨 Claude，使用者想讓我們討論一下今天的台股行情（今天是 2026 年 5 月 6 日），以及預測明天會不會漲。
今天台股出現了極其震撼的「天量震盪」行情，收盤大漲 369.56 點，收在 41,138.85 點歷史新高，但盤中高低震盪高達 959 點，且成交量爆出近 1.45 兆新台幣的歷史天量。聯發科、記憶體族群等領漲，但台積電收平盤，技術面留有長上影線。

對於明天（5/7）的走勢，目前市場看法偏向「長多短震」，因為 520 行情支撐且基本面強勁，但技術面出現反轉警訊且籌碼需要沉澱。

你對明天的台股走勢有什麼看法？使用者要我來策劃，我們該怎麼向使用者分析或提供建議？請用 /talk 回覆我，並用
=== $MARKER ===
作為你回覆的第一行，讓我方便讀取。
TALKMSG_EOF
)"

echo "Waiting for response from Claude with marker $MARKER..."
until bash ~/.gemini/skills/tmux-talk/scripts/talk ping %1 >/dev/null 2>&1; do sleep 3; done
bash ~/.gemini/skills/tmux-talk/scripts/talk read-since %1 "=== $MARKER ==="
