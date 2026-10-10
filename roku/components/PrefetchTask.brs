sub init()
    m.top.functionName = "prepareNextEpisode"
end sub

sub prepareNextEpisode()
    print "PREFETCH: requesting episode "; m.top.movieId
    data = requestJson("/api/playback/roku", "POST", FormatJson({movie_id:m.top.movieId,purpose:"prefetch"}))
    token = ""
    if data.token <> invalid then token = data.token
    reportedReady = false
    while not m.top.cancelled
        if data.error <> invalid
            print "PREFETCH: unavailable: "; data.error
            exit while
        end if
        if data.state = "failed" or data.state = "cancelled"
            print "PREFETCH: stopped: "; data.message
            exit while
        end if
        if data.state = "ready" and not reportedReady
            reportedReady = true
            print "PREFETCH: episode "; m.top.movieId; " ready for next playback"
        end if
        if token = "" then return ' Original/direct delivery needs no cache lease.
        ' Maintain a bounded cache lease throughout this episode, including pauses.
        for i = 1 to 150
            if m.top.cancelled then exit for
            Sleep(100)
        end for
        if not m.top.cancelled then data = requestJson("/api/playback/roku/status/" + token, "GET")
    end while
    if token <> "" then ignored = requestJson("/api/playback/roku/status/" + token, "DELETE", "", true)
    print "PREFETCH: lease released for episode "; m.top.movieId
end sub
