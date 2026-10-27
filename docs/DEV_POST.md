---
title: "Ofrenda: an altar for the names we are afraid of losing"
published: false
description: "A local family altar. Gemma reads a story into a tree, candles mark the missing branches, and a photograph can come back as a quiet ghost. Nothing leaves the laptop."
tags: devchallenge, hf26challenge, gemma, python, ai
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge, Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26).*

*Draft. Before you publish: set `published` to true in the DEV editor, check the challenge page in case the live template has another field, upload the screenshots (DEV will host them), and replace the demo lines below with your GIF or video. Keep the tags `#devchallenge` and `#hf26challenge`.*

## What I built

I built Ofrenda. The tagline is "Remember me."

It is a family altar that runs on a laptop, with no account and no cloud. You tell it about people in ordinary sentences. "My mum is Funke, her dad was Baba Ayo from Ogbomoso, he had a brother Tunde who moved to Ghana." An open-weight Gemma model, running locally through Ollama, turns that into people and relationships and sets them on a tree. You can correct a link, add a photograph, and write the short memory you are afraid will be the one that disappears.

Then the altar looks for the thin places. Tunde has a name and a country and no one beside him. Ofrenda does not invent a wife. It lights a candle and writes a question you could ask someone older: who did he build a life with in Accra, and were there children? One memory is enough to hold him.

If there is a photograph, you can sit with them. MediaPipe, also on the machine, lifts the person out of the picture. They come back translucent, with a soft marigold edge, floating beside you on the webcam, and one of their memories sits on a paper card. I wanted it to feel like the room got quiet. Not a horror effect. A visit.

The family in the repository is fictional. I made the Adeyemis so I could build the altar, and so anyone else can try the candles, without putting real relatives into a public repo. The portraits are drawings the project generates. They are not photographs of anyone.

The code is here: [github.com/Valentinetemi/-Ofrenda](https://github.com/Valentinetemi/-Ofrenda)

### How I read the theme

Ghost in the machine, for me, is the fear that a person becomes a file and then the file is somewhere else. A chat thread. A form. A startup that shuts the lights off. Día de los Muertos, and *Coco* in particular, has the opposite idea. An ancestor fades when the last person who remembers them is gone. Remembering is what makes them visible.

So the ghost in this project is someone we meant to keep. The machine holds the photograph and the story, offline, and only brings the person forward when you ask. The candle is the other half of that. A missing branch is a person halfway to fading: still a name, not yet a story. The software's job is to notice, and to send you back to a human being who might know.

I am a computer science student in Nigeria. The stories I care about are ordinary. They live in the way a sentence starts, "your grandmother used to," and then the rice burns and the story stops. I wanted a place to put the piece down before it thins out, on a machine I can close and still trust.

## Demo

Record the two minutes in [DEMO.md](https://github.com/Valentinetemi/-Ofrenda/blob/main/docs/DEMO.md) and replace this block.

**Video:** *[paste the GIF or the video link here]*

There is no hosted copy. That is the point. The family file never sits on a server I would have to trust. Clone the repo, run `./start.sh`, and open `http://127.0.0.1:8000`.

The fictional altar, after one sentence placed Ama beside Tunde:

![The Adeyemi ofrenda](https://github.com/Valentinetemi/-Ofrenda/raw/main/docs/images/altar.png)

Funke, cut out of her portrait. On my machine MediaPipe did the cut. The webcam picture stays in the browser. With no camera, she stands in a painted night, which is still a visit.

![Ghost mode](https://github.com/Valentinetemi/-Ofrenda/raw/main/docs/images/ghost.png)

Opening someone, to add a memory or a photograph:

![A person, open](https://github.com/Valentinetemi/-Ofrenda/raw/main/docs/images/person.png)

## How I built it

The page is plain HTML, CSS, and JavaScript. The server is Python and FastAPI, bound to localhost. I did not want a framework between me and the one page.

**Gemma does the reading.** The story goes to Ollama's chat API with a short instruction: reply with JSON only, the speaker is a person named Me, a parent link points from parent to child, do not invent people or years. The model name is an environment variable, `OLLAMA_MODEL`, and it defaults to `gemma2:2b`. A larger Gemma is a one-line change when the laptop can take it.

Small models wander, so the reply is not trusted raw. Fences get stripped. A trailing comma is repaired. Years outside 1800 to 2100 are dropped instead of failing the whole story. Relationships to people who were never named are dropped. "Funke" and "funke" become one person. If the JSON is nonsense, the server tries again, up to three times, and shows the model its own error. After that you get a plain sentence, not a half-built tree.

Merging is the other half. Telling the story twice must not clone Funke. A short name lands on someone already on the altar when the match is unique, so "Tunde" is Tunde Adeyemi, and a second "Mama" is not guessed. A link that would cycle the tree, a child who is already the parent's ancestor, is refused. Photographs and memories you typed by hand are left alone.

**The candles are strict about facts and loose about phrasing.** I don't want a model to be the thing that notices a missing child. That is a count over the tree: no spouse and no children on a sibling we barely know, a dead elder with no spouse, a parent whose own parents were never written down. The questions are templates, with a real person's name in them. Funke, not "a relative". If Ollama is up, Gemma may rewrite the wording. The rewrite is checked. An unknown person id is thrown away. A gap the rules did not find cannot appear, because I would rather a stiff question than a fictional uncle. If the model is asleep, the candles still light.

**The ghost is a computer-vision pipeline, and it stays on the machine.** MediaPipe's selfie segmenter, the small float16 model, ships in the repo. For this model the label is `selfie` and there is one confidence mask: how sure each pixel is a person. I still read the labels, so the older two-class card (background, then person) would be handled too. The mask is copied off the native buffer immediately, feathered so the edge is not a pair of scissors, and rejected if it covers almost nothing or almost the whole frame. Illustrations and photos against a flat wall then fall through to a colour key: sample the rim, keep what is not that colour. If that also fails, a soft oval fades the portrait out, so ghost mode still has a shape.

The cut-out is warmed a little, made translucent, and given a marigold ring dilated from the alpha and blurred. That sprite is cached. The browser fetches it once. The webcam is drawn with `getUserMedia` and never posted anywhere. The float is a sine, ten pixels, a period of 3.2 seconds, the same numbers the Python tests assert, served from `/api/ghost/motion` so the page and the tests cannot drift.

There is a mock storyteller behind `OFRENDA_MOCK_LLM=1`. It only understands a few sentence shapes. The tests use it. A laptop that has not installed Ollama yet can still open the altar. It is not the product. Gemma is.

## Why open innovation matters

This is the part I care about.

A family tree is not a prompt I want to send to a company. A photograph of someone who has died is not something I want in a request log, or in a training mix, or on a dashboard I cannot see. Closed models are fluent. They are also somewhere else. The day the key is revoked, or the price changes, or the product is shut, the altar goes dark, and the stories were never really in the house.

Gemma is open-weight, so the reading of the story happens on the laptop. It costs nothing to run once the model is downloaded. It still runs if the network is in a mood. I can swap `gemma2:2b` for another Gemma without rebuilding the page, which matters because not every laptop is the same size. The contract is the JSON, not a vendor's SDK.

MediaPipe is open source, so the cut-out does not bill by the face. The segmenter model is in the repository, Apache licensed, and Ofrenda does not download it again at runtime. I can read the mask, reject a bad one, and fall back. I could not do that with a vision API that only returns a finished sticker.

The tree is one JSON file. I can copy it onto a drive and put the drive in a drawer. That is a feature. An ancestor should not depend on my subscription status.

Open, here, is not a slogan about community, though I want other people to be able to run this and change it. Open is the reason a private thing can stay private. The remembering happens in the room. The machine only holds what the room already knew.

## Prize categories

**Best Use of Gemma.**

Gemma is the storyteller. Every person who arrives through a sentence gets there because the model turned speech into a tree, and when the model is running the questions on the candles are Gemma's words. The gaps are checked in code, on purpose, so the model is used where language matters and not as a database. That is the use I want to be judged on.

## Code

[github.com/Valentinetemi/-Ofrenda](https://github.com/Valentinetemi/-Ofrenda)

MIT licensed. MediaPipe and the selfie segmenter are under Apache 2.0 and credited in the README. The fading ancestor is an idea from Pixar's *Coco*. None of their art is in the project.

If you try it, start with one person the family is about to misremember. One story is enough to stop the fade.
