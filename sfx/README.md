# Sound effects library

Free sound effects from Mixkit (mixkit.co), saved as mp3 and sorted into folders.

## License

Mixkit's Sound Effects Free License: free for YouTube, Facebook and commercial videos. No credit needed.
You can't resell or share the raw sound files as your own sound pack. Using them inside your videos is fine.

## Folders

| Folder | What's inside | Good for |
|---|---|---|
| `creatures/` | roars, growls, wolves, monsters, birds, horses | dinosaurs, monsters, wild animals |
| `animals/` | dogs, cats, farm animals, monkeys, insects | normal animals, farm and pet scenes |
| `human/` | screams, pain, gasps, breathing, crying, heartbeat, footsteps, crowds | fear, injury, chase, crowd scenes |
| `fight/`, `warfare/` | punches, sword hits, blood, explosions, guns, arrows, battle | action and fight scenes |
| `weather/`, `nature/` | rain, thunder, wind, rivers, waterfalls, sea, volcano, fire | outdoor scenes, storms, floods |
| `ambience/` | forest, jungle, night crickets, desert, cave | background loops under narration |
| `transitions/` | whooshes, sweeps, glitches, rewinds, zooms, risers | between images, flashbacks, time skips |
| `horror/` | creaking floors, suspense swells, horror hits | scary moments, tension |
| `bunker/` | doors, locks, metal, alarms, sirens, radio static, electricity | bunker, apocalypse, lab, prison |
| `tech/` | clicks, typing, phones, computers, robots, TV, camera | modern-day, sci-fi, hacker stories |
| `alerts/`, `ui/` | notification dings, beeps, pops, sparkles | subscribe pop-up, text labels, reveals |
| `funny/` | cartoon boings, laughs, fart, silly sounds | comedy and lighthearted stories |
| `transport/` | cars, trains, planes, helicopters, boats, traffic | travel, chase, city stories |
| `home_city/` | kitchen, bathroom, office, school, hospital, city, church | slice-of-life, school, family stories |
| `music/` | short drum hits, bells, choir, orchestra stings, piano | dramatic stingers, intros, endings |
| `game_sports/` | win/lose, game over, coins, sports, casino | game, sports and "level up" stories |
| `misc/` | magic, fireworks, paper, glass, countdown, sci-fi | anything else |

`manifest.json` lists every file with its Mixkit id, original title and size in KB.

## How to use them

### Put them in the script (Story Maker Studio)
Write a tag right before the word where the sound should start. The path is relative to this `sfx` folder.

```
[sfx:fight/sword_slash.mp3 vol=40]       one-shot sound at this word
[sfx:human/fast_heartbeat.mp3 vol=35 fade-out]   fades out at its end
[amb:ambience/scary_woods_at_night.mp3 vol=15 loop fade-in]   background loop, keeps playing
[amb-stop:scary_woods_at_night]          stops that loop here (fades out)
[sfx:human/heartbeat_single.mp3 vol=45 x3]   plays 3 times back to back
Easier: Images & Effects > + sound under an object (search, preview, add).
```

- `vol=` is percent (100 = full). Background loops: 8-20. Hits: 30-60.
- `fade-in` / `fade-out` soften the start / end.
- `loop` repeats the file until its `[amb-stop:...]`, or until the video ends.
- After editing the script, press **Rebuild preview** in the Play tab to hear it. Make video uses the same sound mix.
- A wrong file name is skipped and shows `! sound not found` in the build log.

### Find a sound fast
1. Open the folder that matches the moment (for example `fight/` for a hit).
2. Click a file to preview it in Windows Media Player.
3. Or search the whole `sfx` folder in File Explorer, for example `roar`, `scream`, `door`, `rain`.

### Add them to a video (CapCut, Premiere, DaVinci, any editor)
1. Import the finished video from `bunker-ep01\out\...`.
2. Drag the sound file onto an audio track under the video.
3. Line it up with the image it belongs to, a few frames before the action reads best.
4. Turn the volume down so it never covers the voice:
   - background loops (rain, forest, crickets): about 10-20%
   - one-off hits (roar, punch, explosion): about 40-70%
5. Fade background loops in and out (about 1 second each end).

### Tips
- One strong sound per image is enough. Too many sounds make narration hard to hear.
- Put an ambience loop under a whole scene, then add hits on top for the big moments.
- Use a `transitions/` whoosh when the video slides to the next image.
- Use a `heartbeat` under `[heartbeat]` effects and a `door_knock` under `[knock]` effects in the script.
- Use a `ui/` pop or ding at the subscribe pop-up.
- Thunder and explosions sound bigger if the image has a `shake` or `boom` effect at the same time.

## Getting more sounds

Browse https://mixkit.co/free-sound-effects/, press play to preview, then Download.
Other free sites that are safe for YouTube: Pixabay sound effects, YouTube Studio Audio Library.
Avoid sounds ripped from movies or games; they can get a copyright claim.
