sub Main()
    ep1 = {id:1,kind:"episode",show_key:"show",show_title:"Show",title:"Episode 1",season_number:1,episode_number:1,episode_end:2}
    ep2 = {id:2,kind:"episode",show_key:"show",show_title:"Show",title:"Episode 2",season_number:1,episode_number:2}
    ep3 = {id:3,kind:"episode",show_key:"show",show_title:"Show",title:"Episode 3",season_number:1,episode_number:3}
    copy3 = {id:4,kind:"episode",show_key:"show",show_title:"Show",title:"Episode 3 alternate",season_number:1,episode_number:3}
    ep4 = {id:5,kind:"episode",show_key:"show",show_title:"Show",title:"Episode 1",season_number:2,episode_number:1}
    extra = {id:6,kind:"episode",show_key:"show",show_title:"Show",title:"Extra",season_number:-1,episode_number:0}
    library = [{id:"show",kind:"show",seasons:[{episodes:[ep1,ep2,ep3,copy3]},{episodes:[ep4]},{episodes:[extra]}]}]
    check(NextAutoplayItem(ep1,library,{}).id = 3,"Combined episode skips its covered episode")
    check(NextAutoplayItem(ep3,library,{}).id = 5,"Next season selected without duplicate encode")
    check(NextAutoplayItem(ep4,library,{}) = invalid,"Series ends without autoplaying extras")
    check(NextAutoplayItem(extra,library,{}) = invalid,"Extras do not start an episode chain")
    check(NextAutoplayItem(ep1,library,{"3":true,"4":true}).id = 5,"Already played episodes excluded")
    movies = [
        {id:10,title:"Current",genres:["Action","Comedy"],duration:1200}
        {id:11,title:"Similar",genres:["Action"],duration:1200}
        {id:12,title:"Best",genres:["Action","Comedy","Action"],duration:1200}
        {id:13,title:"Bumper",genres:["Action","Comedy"],duration:5}
        {id:14,title:"Unrelated",genres:["Horror"],duration:1200}
    ]
    check(NextAutoplayItem(movies[0],movies,{}).id = 12,"Most shared genres recommended")
    check(NextAutoplayItem(movies[0],movies,{"12":true}).id = 11,"Visited movie not repeated")
    check(NextAutoplayItem(movies[0],movies,{"12":true,"11":true}) = invalid,"No unrelated or bumper autoplay")
    check(not AutoplayNeedsConfirmation(0),"Initial manual play permits autoplay")
    check(not AutoplayNeedsConfirmation(2),"Third automatic transition is allowed")
    check(AutoplayNeedsConfirmation(3),"Fourth automatic transition requires confirmation")

    ' Exercise the real controller with mocked nodes and playback entrypoints.
    m.nextUp = {visible:false,remaining:0,SetFocus:function(flag):m.focus=flag:end function}
    m.video = {state:"playing",duration:1200,position:1175,trickPlayBar:{visible:false},control:"",SetFocus:function(flag):m.focus=flag:end function}
    m.mode="video"
    m.nextItem=movies[1]
    m.nextUpShown=false
    m.nextUpReleased=false
    m.autoplayCancelled=false
    updateNextUp()
    check(m.nextUp.visible and m.nextUp.remaining=25,"Countdown appears at 25 seconds remaining")
    m.video.state="paused"
    updateNextUp()
    check(m.nextUp.remaining=25,"Paused countdown does not advance")
    m.video.position=900
    updateNextUp()
    check(not m.nextUp.visible,"Rewinding out of final window hides countdown")
    m.video.state="playing"
    m.video.position=1190
    m.video.trickPlayBar.visible=true
    updateNextUp()
    check(not m.nextUp.visible,"Countdown does not steal active timeline focus")
    m.video.trickPlayBar.visible=false
    updateNextUp()
    cancelAutoplay()
    check(m.autoplayCancelled and not m.nextUp.visible,"Back cancels current autoplay")

    m.autoplayCount=2
    m.nextItem=movies[1]
    m.playbackTask=invalid
    m.video.state="playing"
    beginAutoplayTransition()
    check(m.mode="transition" and m.video.control="stop","Early next waits for old video to stop")
    check(m.autoplayCount=3,"Exactly third transition counted")
    launchQueuedAutoplay()
    check(m.opened.id=11 and m.playStarted,"Next uses existing movie/preparation entrypoints")
    m.opened=invalid
    launchQueuedAutoplay()
    check(m.opened=invalid,"Duplicate stop notification cannot start twice")

    m.confirmingAutoplay=true
    m.autoplayDialog={close:false}
    m.autoplayCount=3
    m.nextItem=movies[2]
    m.video.state="finished"
    event={GetData:function():return 0:end function}
    onAutoplayConfirmation(event)
    check(m.autoplayCount=1 and m.opened.id=12,"Yes resets counter and permits next title")
    check(not m.confirmingAutoplay and m.autoplayDialog.close,"Prompt closes once approved")
    m.confirmingAutoplay=true
    m.detailsShown=false
    onAutoplayPromptClosed()
    check(m.autoplayCancelled and m.detailsShown,"Dismissal stops rather than continuing unattended")
    current = {kind:"episode",filename:"Show.S01E01.mkv"}
    nextEpisode = {id:2,kind:"episode",filename:"Show.S01E02.MKV"}
    check(CanPrepareNextEpisode(current,nextEpisode,false,false),"Next MKV episode is eligible")
    check(CanPrepareNextEpisode(current,{kind:"episode",filename:"episode.avi"},false,false),"AVI next episode uses existing compatibility preparation")
    check(not CanPrepareNextEpisode(current,{kind:"episode",filename:"episode.mp4"},false,false),"Direct MP4 needs no preparation")
    check(not CanPrepareNextEpisode(current,nextEpisode,true,false),"Original audio choice suppresses lookahead")
    check(not CanPrepareNextEpisode(current,nextEpisode,false,true),"Cancelled autoplay suppresses lookahead")
    check(not CanPrepareNextEpisode({kind:"movie"},nextEpisode,false,false),"Movies do not trigger series preparation")
    check(not CanPrepareNextEpisode(current,invalid,false,false),"Series ending does not queue anything")
    existing = {movieId:2,cancelled:false}
    m.prefetchTask = existing
    m.mode="video"
    m.video.state="playing"
    m.selected=current
    m.nextItem=nextEpisode
    m.audioOriginal=false
    m.autoplayCancelled=false
    startNextEpisodePreparation()
    check(m.prefetchTask.movieId=2 and not existing.cancelled,"Playback updates do not duplicate preparation")
    stopNextEpisodePreparation()
    check(existing.cancelled and m.prefetchTask=invalid,"Leaving playback releases the task")
    m.prefetchTask={movieId:2,cancelled:false}
    pending=m.prefetchTask
    resetAutoplay()
    check(pending.cancelled and m.prefetchTask=invalid,"Manual title selection cancels old speculation")
    ' Retain next-target lease while stopping old Video to prevent conversion restart.
    m.prefetchTask={movieId:2,cancelled:false}
    m.nextItem=nextEpisode
    m.video.state="playing"
    pending=m.prefetchTask
    beginAutoplayTransition()
    check(not pending.cancelled,"Autoplay handoff retains preparation until new playback acquires it")
    stopNextEpisodePreparation()
    movieCredits={kind:"movie",credits_start:6500}
    check(MovieNextWindow(movieCredits,7200,6500),"Movie next window begins at credits")
    check(not MovieNextWindow(movieCredits,7200,6499),"Movie prompt stays hidden before credits")
    check(not MovieNextWindow({kind:"episode",credits_start:6500},7200,6500),"Episodes ignore movie markers")
    check(MovieNextWindow({kind:"episode"},7200,7170),"Episode final-30-second window preserved")
    check(not MovieNextWindow({kind:"movie"},7200,6500),"Unmarked movie does not guess credits start")
    check(MovieNextWindow({kind:"movie",credits_start:8000},7200,7180),"Invalid credit marker uses fallback")
    check(not MovieNextWindow(movieCredits,0,10),"Unknown duration cannot show prompt")
    m.selected=movieCredits
    m.mode="video"
    m.video.state="playing"
    m.video.duration=7200
    m.video.position=6500
    m.nextItem=movies[1]
    m.autoplayCancelled=false
    m.nextUpReleased=false
    hideNextUp()
    updateNextUp()
    check(m.nextUp.visible and m.nextUp.remaining=700,"Controller offers next movie at credits, preserves end countdown")
    m.video.position=6400
    updateNextUp()
    check(not m.nextUp.visible,"Seeking before credits hides next movie")
    print "PASS: Autoplay policy and controller"
end sub

sub openMovie(item as object)
    m.opened=item
    m.mode="details"
end sub
sub onPlay()
    m.playStarted=true
end sub
sub showDetails()
    m.detailsShown=true
end sub
sub check(condition as boolean, message as string)
    if not condition
        print "FAIL: ";message
        stop
    end if
end sub
