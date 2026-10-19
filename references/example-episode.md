# Example episode (shape and density reference)

Fictional PR: "Add stale-while-revalidate caching to token price fetches"
(~430 words, about 3:10 spoken). Copy the structure and density, not the content.

```
JASON: [excited] Besties, we've got a spicy one. PR forty-two eighteen adds stale-while-revalidate caching to token prices. Short version: the price screen stops hanging on a spinner. Friedberg, what's the pain?
FRIEDBERG: Every time you opened a token page, use token price fired a fresh request to the price service. P90 was about nine hundred milliseconds, and on bad networks the screen just sat there.
CHAMATH: [interrupting] And that's the first screen after a push notification. That's where people decide to trade or bounce.
JASON: Okay, explain it like I'm five before you go full Rain Man.
FRIEDBERG: [laughs] Think of a deli with a chalkboard of prices. Old way, every customer who asks makes the guy run to the back and check. New way, he reads the chalkboard. If it's a bit old, he still reads it, but sends a kid to the back to update it for the next person.
CHAMATH: And if the chalkboard's really old, you wait for the guy. Got it.
JASON: So mechanically, how does it work?
FRIEDBERG: [thoughtful] Step one, there's a new price cache module. That's the chalkboard: an in-memory map keyed by chain ID plus contract address, storing the price and a fetched-at timestamp. Step two, use token price reads the cache first. Younger than fifteen seconds, it returns it and stops. Step three, between fifteen seconds and five minutes, it returns the stale value immediately and kicks off a background refetch. That's the kid. Step four, older than five minutes, it's a miss and you get the spinner like before.
JASON: Wait, what if two components ask for the same token at the same time?
FRIEDBERG: Good question. There's an in-flight map, so concurrent requests for the same key share one promise. No thundering herd.
CHAMATH: Let me just say this, because it's the whole ballgame. Fifteen seconds fresh, five minutes stale. Those two numbers define what the user sees. Get them wrong and you're showing a price that's five minutes old on a volatile token.
SACKS: [skeptical] Yeah, and that's my problem. Look, I'm going to push back. You're showing a stale price on a trading app. The steelman for the other approach is skeleton loaders plus server-side caching. Slower, but never wrong.
FRIEDBERG: It's not used for execution, though. The swap quote still fetches live. This is only the display price.
SACKS: Fine, but there's no sign on the chalkboard saying when it was written. And it's in-memory, so a cold start gets nothing. You're paying for this in user trust on the exact tokens that move fastest.
CHAMATH: [laughs] He's not wrong. A staleness indicator should be a fast follow.
JASON: Bottom line, the money screen stops making you wait, and the price you see can be up to five minutes old. I'll bet the staleness badge ships within a sprint.
SACKS: [sarcastic] I'll take the over.
JASON: [laughs] Love you, besties.
```
