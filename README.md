# ytstore

A Youtube-Based Storage Service.

# Prototyping
I've made a prototype which can encode any file into a video (webm)  
I've successfully recovered a 2MB image from youtube, which you can see in [the prototype folder](/prototype)  

In the [videos](/prototype/videos), you'll notice that the webm file is astronomically large, 79MB for about 1 second, that's because of extremely high quality video, that's needed to survive re-encoding and compression, down to 23MB (check downloaded.mp4), the compression doesn't cause any major corruption.2

manifest.json contains the decoding metadata for decoding the video/frames, however it isn't exactly necessary for decoding.

In the [images](/prototype/images), you'll notice the recovered image is 0.02MB bigger than the original image, this is a common thing in all my prototypes, which is probably due to corrupted bytes.

### Scripts
Usage of the scripts,

NOTE: encoder will only output a video if ffmpeg is on PATH, otherwise, it'll only generate the frames, same goes for decoder, it needs ffmpeg to decode a video

encoder: `python encoder.py cool.file output_dir` (you can modify the internal video format, by passing cli args, check the first docstring in encoder.py)  
decoder: `python decoder.py encoded.webm recovered.file` (if you modified the internal video format, you'll need to match it here as well)  
decoder (using frames directory): `python decoder.py frames_directory recovered.file` (this is incase you don't have ffmpeg)  

The encoder will always output a webm ("encoded.webm"), however the decoder will accept any video format.  
The encoder also outputs a /frames directory which contains each frame, you may/may not need this.

