' Start only after the current Video enters playing; never delay its first frame.
function CanPrepareNextEpisode(current as dynamic, nextItem as dynamic, original as boolean, cancelled as boolean) as boolean
    if original or cancelled then return false
    if current = invalid or nextItem = invalid then return false
    if current.kind <> "episode" or nextItem.kind <> "episode" then return false
    if nextItem.filename = invalid then return false
    extension = LCase(Right(nextItem.filename, 4))
    return extension = ".mkv" or extension = ".avi"
end function

sub stopNextEpisodePreparation()
    if m.prefetchTask <> invalid
        m.prefetchTask.cancelled = true
        m.prefetchTask = invalid
    end if
end sub

sub startNextEpisodePreparation()
    if m.mode <> "video" or m.video.state <> "playing" then return
    if not CanPrepareNextEpisode(m.selected, m.nextItem, m.audioOriginal, m.autoplayCancelled) then return
    if m.prefetchTask <> invalid
        if m.prefetchTask.movieId = m.nextItem.id then return
        stopNextEpisodePreparation()
    end if
    m.prefetchTask = CreateObject("roSGNode", "PrefetchTask")
    m.prefetchTask.baseUrl = ServerUrl()
    m.prefetchTask.movieId = m.nextItem.id
    m.prefetchTask.control = "RUN"
    print "PREFETCH: preparing next: "; AutoplayLabel(m.nextItem)
end sub
