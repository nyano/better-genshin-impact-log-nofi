(async function () {
    const logText = settings.inputValue;
    log.info(logText);
	notification.send(logText);
})();
