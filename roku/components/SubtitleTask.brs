sub init()
    m.top.functionName = "fetchSubtitles"
end sub
sub fetchSubtitles()
    data = requestJson("/api/movies/" + m.top.movieId.ToStr() + "/subtitles", "GET", "", false, 5000)
    if m.top.cancelled then return
    intro = requestJson("/api/movies/" + m.top.movieId.ToStr() + "/intro", "GET", "", false, 3000)
    if intro.intro <> invalid then data.intro = intro.intro
    credits = requestJson("/api/movies/" + m.top.movieId.ToStr() + "/credits", "GET", "", false, 3000)
    if credits.start <> invalid then data.credits_start = credits.start
    if not m.top.cancelled then m.top.result = data
end sub
