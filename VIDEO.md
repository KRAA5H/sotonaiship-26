# The video: trailer grammar, real product spine

Companion to `PLAN.md`. Read the constraint first, because it decides the whole edit.

## The one rule that shapes everything

The submission page, verbatim:

> It must show the real product working: a screen recording of the live product. **Mock-ups or slides alone do not count as a demo.**

So a pure trailer loses C3, which is the heaviest criterion at 25% and the tie-breaker. A pure screen recording loses the room in Stage 1, where 70% of the vote is the audience. The answer is a **trailer with a real product spine**: AI-generated b-roll for the world and the emotion, continuous real screen recording for the workflow, and no more than about 35 seconds of the 160 that is not the actual product.

Two hard rules inside that:

1. **Never generate an AI image of the product UI.** A photoreal fake dashboard is a mock-up, and a judge who spots it will say so out loud. AI imagery is for potholes, kerbs, vans, tide lines and people. The interface is only ever real pixels.
2. **Cut for pace, not to hide steps.** Jump cuts on the real footage are fine. Cutting from "report arrives" to "work order exists" without the intermediate visible is not, so the step counter HUD carries the story across the cut.

State in the submission: **video 2:40 plus a 20 second live call to action.** The organisers ask which format, and the live 20 seconds is worth a lot of audience money. Do not forget to declare it.

---

## Beat sheet, 2:40

`REAL` means live product capture. `AI` means generated b-roll. Nothing else is allowed.

| Time | Visual | Audio | Text on screen | Type |
|---|---|---|---|---|
| 0:00 | Black. One vibration. White type fades in. | Room tone, then the buzz | `Southampton. 10,948 fly-tipping reports. One year.` | AI (title) |
| 0:05 | Macro of a wheel entering a crater, slow motion. Rain on tarmac | Low drone note enters | `Nobody knows where to send them.` | AI |
| 0:10 | Fly-tipped mattress on a kerb at dusk, council estate backdrop. Cut on the beat to a fluorescent-lit empty desk and a stack of papers | Drone builds | none | AI |
| 0:16 | A hand holding a phone, thumb typing. Screen glow on the face, out of focus | Music drops out, single phone key clicks | `So we put the council in the chat.` | AI |
| 0:20 | **REAL phone screen**: Messages thread. Resident sends photo and "massive pothole outside the school on Weston Lane, nearly took my wheel off" | Keys, message sent whoosh | `REAL iMESSAGE` corner label | REAL |
| 0:27 | **REAL**: agent replies, one question. Resident answers. Agent: "Logged. Ref KB-1042. Priority urgent." | Notification chime | `1 question. 7 seconds.` | REAL |
| 0:38 | **REAL console, wide**: report lands in the inbox, card animates in | Beat returns, harder | `STEP 1 of 11` HUD | REAL |
| 0:44 | **REAL**: photo opens, evidence highlight boxes the crater and the kerb line | none | `reads the photo, not just the words` | REAL |
| 0:52 | **REAL**: duplicate card slides in, "4 reports, 38m, 2 days". Cluster merges, priority badge ticks up | Low impact hit | `finds the other 4 people who reported it` | REAL |
| 1:02 | **REAL**: work order call. Terminal or network panel shows the POST and a 201 with a work order id. Cut to job appearing in Tomorrow list, 08:00 slot, crew assigned | Typing, then a solid thunk | `creates the job in the works system` | REAL |
| 1:18 | **REAL**: Tomorrow list, three nearby jobs snap into one route, map draws the line | none | `batches the route` | REAL |
| 1:26 | **REAL predictive pane**: tide 4.9m Thursday, 18mm rain, three gullies pulled forward to today | Tide-like swell | `and works tomorrow before it is a problem` | REAL |
| 1:40 | **REAL phone**: "the pothole on Weston Lane has been repaired". Thumb scrolls back up to their own photo | Warm chord | `closed loop` | REAL |
| 1:50 | Fast trailer cuts, 1.2s each: crew van, depot gate, tide line at Weston Shore, a school crossing | Drums | none | AI |
| 1:58 | Numbers, one per cut, big, no clutter | Drums continue | `0.94 vs 0.61 macro F1` `4x duplicate catch` `£0.006 per report` `2.5 min saved` | AI (type) |
| 2:10 | **REAL failure case**: photo of a private car park. Agent declines to guess, names the likely owner, flags human review | Music stops dead | `When it does not know, it says so.` | REAL |
| 2:18 | **REAL failure case**: classifier timeout, "degraded", keyword baseline still logs the report | Single soft beep | `Nothing is ever lost.` | REAL |
| 2:26 | Back to the first phone, held in the same hand as 0:16, now showing the completion message. Full circle | Music resolves | `One text. One job. One closed loop.` | AI plus REAL insert |
| 2:36 | Logo on black, one line under it | Final chord, tail | `Kerbside. Text the council.` | AI (title) |
| 2:40 | End. Cut to live: "Text this number now, and watch it land on the screen." | Live mic | The number, huge | LIVE |

Footage audit: REAL runs from 0:20 to 1:50 and 2:10 to 2:26 plus the insert. That is about 1:46 of 2:40. AI is the bookends and the two interludes, which is exactly the grammar a trailer needs and far inside the risk line.

---

## The 20 second live ending

Rehearse this once. Do not improvise it.

> "That was a real report. If you are in the room, text this number a photo of anything broken between here and your hotel, and watch the screen. We will leave it running all afternoon."

Then stand still for three seconds. The silence is what makes the room look at their phones. The console is on the projector, so the room watches their own reports queue up. That is the Stage 1 pitch, and it costs twenty seconds.

---

## The AI b-roll shot list, with prompts

Consistent look: overcast Southampton light, muted teal and rust palette, 35mm, shallow depth of field, film grain, no text, no logos, no faces in focus. Generate 3 variants of each and keep the best.

1. `macro shot, car tyre entering a deep pothole on a wet residential street, overcast British daylight, shallow depth of field, 35mm film grain, muted colours, no text`
2. `discarded mattress and bin bags fly-tipped on a suburban kerb at dusk, terraced houses, wet pavement reflections, documentary photography, muted, no text`
3. `empty council open-plan office at night, one desk lamp on, stacks of printed forms, fluorescent corridor light, wide angle, muted, no people, no text`
4. `close up of hands holding a smartphone, screen glow on skin, blurred kitchen background, night, warm practical light, no readable screen content`
5. `white highways maintenance van parked on a residential street, two workers in high vis with a shovel, overcast, documentary, mid distance, faces not visible, no text`
6. `high tide meeting a concrete sea wall at Weston Shore Southampton, grey water, wet steps, overcast, long lens, no people, no text`
7. `school crossing markings on wet asphalt, zebra crossing, empty street, early morning, overcast, low angle, no text`

Generate nothing that contains readable UI, a phone screen, a dashboard, a logo or a legible sign. Regenerate if any of those appear.

---

## Capture checklist for the REAL footage

Record these as separate clips in one session, so the story stays coherent and the same job references appear throughout.

- [ ] Phone: use iOS screen recording, or QuickTime with the cable and "record iPhone screen". Clean status bar (9:41, full battery, no notifications). Do not disturb on. Brightness at 100 percent so the recording is not dim.
- [ ] Put the phone capture inside a simple device frame in the edit, sized to about 40 percent of a 1920x1080 canvas, next to the console. Split screen is the whole visual idea: the resident on the left, the machine on the right.
- [ ] Console: 1920x1080 browser window, zoom 110 percent so text survives compression, no bookmarks bar, no other tabs.
- [ ] Terminal or network panel for the work order call: font at 18pt minimum, show the request body and the 201 response.
- [ ] Record the predictive pane with the timestamp visible, and the tide and rain source labels on screen.
- [ ] Record both failure cases twice each, once as a clean take and once as a backup. They are the clips most likely to be fluffed.
- [ ] Record the resident completion text last, so the phone thread contains the full story.
- [ ] Capture at 60fps if the console animates, and export at 30.

Shoot the whole thing in one 40 minute block at 10:30. Do not shoot at 12:00.

---

## Edit and finishing

- **Assembly**: CapCut Desktop or DaVinci Resolve. If someone codes confidently, Remotion gives exact frame control and makes the numeric cards trivial, but do not learn it this weekend.
- **Voiceover**: one of us, recorded in a quiet room with a phone or a headset. Trailer voiceover should be sparse, around 90 words for the whole thing. Claude can draft the lines, but a synthetic voice reads as an advert and undermines the "real residents" claim. Use your own.
- **Voiceover lines, about 90 words total**: keep them as fragmentary as the on-screen text. Never narrate what is already visible.
- **Music**: one licensed track from the YouTube Audio Library or Pixabay, cut to the beat map above. Trailer music wants a single build, one drop, then silence at the failure beat, which is the strongest moment in the edit.
- **Mix**: voiceover at -6dB peak, music -18dB under voice, total loudness around -14 LUFS. Judges watch on laptops.
- **Captions**: burned in, large, high contrast. Assume muted playback on a phone in a noisy room.
- **Export**: 1920x1080, H.264, 24 or 30fps, around 10 Mbps. Under 3:00 exactly, so trim the last frame if needed.
- **Upload**: unlisted, before 12:00. Title it properly, put the repo and the team name in the description, and set a thumbnail that is one frame of the real console, not an AI image.

---

## Trailer grammar worth stealing, in three notes

1. **One repeated image.** The phone in the hand appears at 0:16 and again at 2:26 with a different message on it. Repetition with a difference is what makes a 2 minute video feel like it closed a loop rather than listed features.
2. **Silence is a punchline.** Kill the music for the four seconds of the failure case. It is the single most trusted moment in the video, and it only works because the rest is loud.
3. **Numbers as cuts, not as a slide.** Four big numbers, one per cut, no bullet points. A slide at 1:58 is the moment judges stop watching.

---

## Fallback if the build is late

If the loop is not clean by 11:00, record what exists, in this order of priority: the phone conversation, the report landing with the photo evidence, the work order 201, the resident completion text. Those four clips alone are a defensible 90 second demo. Cut the predictive pane and the second failure case, keep the first, and say in the video what is not shown yet. Honesty about the gap scores better than a fake step.
