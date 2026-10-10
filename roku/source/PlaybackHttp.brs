function requestJson(path as string, method as string, body = "" as string, cleanup = false as boolean, timeoutMs = 30000 as integer) as object
    port = CreateObject("roMessagePort")
    transfer = CreateObject("roUrlTransfer")
    transfer.SetMessagePort(port)
    transfer.SetUrl(m.top.baseUrl + path)
    transfer.AddHeader("X-Media-Client", "roku")
    transfer.AddHeader("Content-Type", "application/json")
    transfer.RetainBodyOnError(true)
    transfer.SetRequest(method)
    if method = "POST"
        started = transfer.AsyncPostFromString(body)
    else
        started = transfer.AsyncGetToString()
    end if
    if not started then return {error: "Could not start playback request."}
    timer = CreateObject("roTimespan")
    while timer.TotalMilliseconds() < timeoutMs
        if m.top.cancelled and not cleanup
            transfer.AsyncCancel()
            return {error: "Cancelled."}
        end if
        event = Wait(250, port)
        if Type(event) = "roUrlEvent"
            code = event.GetResponseCode()
            data = ParseJson(event.GetString())
            if code >= 200 and code < 300
                if Type(data) = "roAssociativeArray" then return data
                return {}
            end if
            message = "Playback request failed (HTTP " + code.ToStr() + ")."
            if Type(data) = "roAssociativeArray"
                if GetInterface(data.detail, "ifString") <> invalid then message = data.detail
            end if
            return {error: message}
        end if
    end while
    transfer.AsyncCancel()
    return {error: "Media server timed out. Press Play to retry."}
end function

