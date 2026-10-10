sub init()
    m.top.functionName = "preparePlayback"
end sub

sub preparePlayback()
    print "AUDIO: requesting compatible playback for movie "; m.top.movieId
    session = requestJson("/api/playback/sessions", "POST", FormatJson({movie_id:m.top.movieId,client_id:MediaClientId(),client_type:"roku",intent:m.top.intent}), false, 3000)
    body = {movie_id:m.top.movieId,mode:m.top.mode}
    if session.session_id <> invalid then body.session_id = session.session_id
    source = requestJson("/api/movies/" + m.top.movieId.ToStr(), "GET", "", false, 3000)
    if source.video_profile <> invalid and source.video_level <> invalid and source.video_level > 0
        codec = ""
        divisor = 10
        if source.video_codec = "h264" then codec = "mpeg4 avc"
        if source.video_codec = "hevc"
            codec = "hevc"
            divisor = 30
        end if
        if codec <> ""
            device = CreateObject("roDeviceInfo")
            profile = LCase(source.video_profile)
            if profile = "constrained baseline" then profile = "baseline"
            answer = device.CanDecodeVideo({codec:codec,profile:profile,level:(source.video_level / divisor).ToStr()})
            if answer <> invalid and answer.result <> invalid then body.capabilities = {source_video_supported:answer.result}
        end if
    end if
    data = requestJson("/api/playback/roku", "POST", FormatJson(body))
    token = ""
    if data.token <> invalid then token = data.token
    ready = false
    while not m.top.cancelled
        if data.error <> invalid
            if not ready then m.top.result = data
            print "AUDIO ERROR: "; data.error
            exit while
        end if
        if data.state = "failed" or data.state = "cancelled"
            m.top.result = {error: data.message}
            exit while
        end if
        if data.state = "ready" and not ready
            ready = true
            subtitles = requestJson("/api/movies/" + m.top.movieId.ToStr() + "/subtitles", "GET", "", false, 5000)
            if subtitles.tracks <> invalid then data.subtitle_tracks = subtitles.tracks
            intro = requestJson("/api/movies/" + m.top.movieId.ToStr() + "/intro", "GET", "", false, 3000)
            if intro.intro <> invalid then data.intro = intro.intro
            credits = requestJson("/api/movies/" + m.top.movieId.ToStr() + "/credits", "GET", "", false, 3000)
            if credits.start <> invalid then data.credits_start = credits.start
            if session.session_id <> invalid
                data.session_id = session.session_id
                data.resume_position = session.resume_position
            end if
            m.top.result = data
            print "AUDIO: ready "; data.stream_url
        else if not ready
            message = "Preparing compatible playback"
            if data.progress <> invalid then message = message + " (" + data.progress.ToStr() + "%)"
            m.top.statusText = message + Chr(10) + "First playback may take a few minutes. Back cancels."
        end if
        if token = "" then return
        ' Keep the cache entry leased while Video plays. No networking on the render thread.
        ticks = 10
        if ready then ticks = 150
        for i = 1 to ticks
            if m.top.cancelled then exit for
            Sleep(100)
        end for
        if not m.top.cancelled then data = requestJson("/api/playback/roku/status/" + token, "GET")
    end while
    if not ready and session.session_id <> invalid
        ignored = requestJson("/api/playback/sessions/" + session.session_id + "/end", "POST", FormatJson({sequence:0,position:0,duration:0,state:"cancelled"}), true, 3000)
    end if
    if token <> "" then ignored = requestJson("/api/playback/roku/status/" + token, "DELETE", "", true)
end sub
