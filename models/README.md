# Local models

`selfie_segmenter.tflite` is Google's MediaPipe Selfie Segmenter (square input, float16). It is the model that lifts a person out of a photograph for ghost mode.

Downloaded from the MediaPipe model bucket:

https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite

MediaPipe and this model are under the Apache License 2.0. See the model card linked from the [image segmenter guide](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter).

The file is stored in the repo so a laptop can cut a portrait out with no network after install. Ofrenda does not download it again at runtime.

Language models are not stored here. Gemma is pulled separately with Ollama (`ollama pull gemma2:2b`, or whatever `OLLAMA_MODEL` names).
