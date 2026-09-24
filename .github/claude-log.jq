# Human-readable progress from `claude -p --output-format stream-json --verbose`:
# one line per tool call or message, and the final result with turns and duration.
if .type == "assistant" then
  (.message.content[]? |
    if .type == "text" then "[claude] " + (.text | gsub("\n"; " ") | .[0:400])
    elif .type == "tool_use" then "[tool] " + .name + " " + (.input | tostring | .[0:240])
    else empty end)
elif .type == "result" then
  "[result] " + (.subtype // "") + " turns=" + (.num_turns | tostring)
  + " duration=" + ((.duration_ms // 0) / 60000 | floor | tostring) + "min\n" + (.result // "")
else empty end
