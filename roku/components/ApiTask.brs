sub init()
    m.top.functionName = "fetchMovies"
end sub

sub fetchMovies()
    if m.top.scanUrl <> ""
        print "API: scanning library before refresh"
        error = scanBeforeRefresh(m.top.scanUrl)
        if error <> ""
            m.top.result = {error: error}
            return
        end if
    end if
    print "API: requesting movie library "; m.top.url
    port = CreateObject("roMessagePort")
    transfer = CreateObject("roUrlTransfer")
    transfer.SetMessagePort(port)
    transfer.SetUrl(m.top.url)
    transfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    transfer.InitClientCertificates()
    transfer.AddHeader("Accept", "application/json")
    transfer.AddHeader("Cache-Control", "no-cache")
    if not transfer.AsyncGetToString()
        m.top.result = {error: "Could not start HTTP request"}
        return
    end if
    event = Wait(15000, port)
    if event = invalid
        transfer.AsyncCancel()
        m.top.result = {error: "Request timed out after 15 seconds"}
        return
    end if
    if Type(event) <> "roUrlEvent"
        m.top.result = {error: "Unexpected HTTP event"}
        return
    end if
    code = event.GetResponseCode()
    if code <> 200
        message = "HTTP " + code.ToStr() + ": " + event.GetFailureReason()
        print "API ERROR: "; message
        m.top.result = {error: message}
        return
    end if
    movies = ParseJson(event.GetString())
    if Type(movies) <> "roArray"
        m.top.result = {error: "Server did not return a movie array"}
        return
    end if
    for each movie in movies
        if Type(movie) <> "roAssociativeArray"
            m.top.result = {error: "Invalid movie entry"}
            return
        end if
        if movie.id = invalid or movie.title = invalid
            m.top.result = {error: "Movie is missing required fields"}
            return
        end if
        if GetInterface(movie.title, "ifString") = invalid
            m.top.result = {error: "Movie title or URL is not a string"}
            return
        end if
        if movie.kind = "show"
            if Type(movie.seasons) <> "roArray"
                m.top.result = {error: "Show is missing seasons"}
                return
            end if
        else if GetInterface(movie.stream_url, "ifString") = invalid
            m.top.result = {error: "Movie is missing its playback URL"}
            return
        end if
    end for
    print "API: received "; movies.Count(); " movies"
    m.top.result = {movies: movies}
end sub

' Runs only for an explicit refresh, on this Task thread rather than the UI thread.
function scanBeforeRefresh(url as string) as string
    port = CreateObject("roMessagePort")
    transfer = CreateObject("roUrlTransfer")
    transfer.SetMessagePort(port)
    transfer.SetUrl(url)
    transfer.SetCertificatesFile("common:/certs/ca-bundle.crt")
    transfer.InitClientCertificates()
    transfer.AddHeader("Content-Type", "application/json")
    transfer.AddHeader("X-Media-Client", "roku")
    transfer.SetRequest("POST")
    if not transfer.AsyncPostFromString("{}") then return "Could not start library scan."
    event = Wait(120000, port)
    if event = invalid
        transfer.AsyncCancel()
        return "Library scan is taking longer than two minutes. The server may still be scanning; press OK to retry."
    end if
    if Type(event) <> "roUrlEvent" then return "Unexpected library scan response."
    if event.GetResponseCode() <> 200
        return "Library scan failed (HTTP " + event.GetResponseCode().ToStr() + "). Check the server and media folder, then press OK to retry."
    end if
    print "API: library scan complete "; event.GetString()
    return ""
end function
