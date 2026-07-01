//cpApp.controller('DailyHomiliesController', function($scope, $location, $routeParams, $log, $filter, $uibModal) {
cpApp.controller('DailyHomiliesController', function($scope, $location, $routeParams, $log, $filter, $uibModal) {

  $scope.showingAllTags = false;
  if ($location.search().dt) {
    $scope.dt = new Date($location.search().dt);
  } else {
    $scope.dt = new Date();
  }

  $scope.yearOptions = [
    {name : "2024", id : 2026},
    {name : "2024", id : 2025},
    {name : "2024", id : 2024},
    {name : "2023", id : 2023},
    {name : "2022", id : 2022},
    {name : "2021", id : 2021},
    {name : "2020", id : 2020},
    {name : "2019", id : 2019},
    {name : "2018", id : 2018},
    {name : "2017", id : 2017},
    {name : "2016", id : 2016},
    {name : "2015", id : 2015},
    {name : "2014", id : 2014}];
    $scope.yearStr = $scope.yearOptions[0].id;

  $scope.maxTagCount = 0;

  //TODO - 
  //
  //  FEATURES:
  //    2 -have a date picker?
  //    3 - pick the date off the url
  $scope.parseLiturgicalDay = function(homiliesByName, homiliesArr, c, j) {
    //$log.debug(c);
    /*
    if (c['liturgical_year'] && j == 0) {
      homiliesArr.push(c.liturgical_day[j]);
      homiliesByName[c.liturgical_day[j]] = c;
      //homiliesByName[c.liturgical_day[j] + '-' + c.liturgical_year] = c;
    } else {
      homiliesArr.push(c.liturgical_day[j]);
      homiliesByName[c.liturgical_day[j]] = c;
    }
    */
    if (!$scope['allTags']) {
      $scope.allTags = {};
    }
    if (c.tags != null) {
      tags = c.tags.split(' ');
      if (tags != null && tags.length > 0) {
        for (var i=0; i < tags.length; i++) {
          //tag = tags[i].replace(new RegExp('_', 'g'), ' ');
          tag = tags[i]; //.replace(new RegExp('_', 'g'), ' ');
          if (tag != "") {
            if ($scope.allTags[tag]) {
              $scope.allTags[tag]++;
              if ($scope.allTags[tag] > $scope.maxTagCount) {
                $scope.maxTagCount = $scope.allTags[tag];
              }
            } else {
              $scope.allTags[tag] = 1;
            }
          }
        }
      }
    }
    if (!c.hasOwnProperty('searchText')) {
      c['searchText'] = c.liturgical_day[j] + ' ' + c.tags;
      homiliesArr.push(c);
    } else {
      c['searchText'] = c['searchText'] + ' ' + c.liturgical_day[j];
      //c['searchText'] = c.liturgical_day[j];
    }
    //$log.debug(c.searchText);
    homiliesByName[c.liturgical_day[j]] = c;
    //$log.debug(c.liturgical_day[j]);
    /*
    //DH2015Y13WeekOrdTFri(FeastofThomasApostle).wav
    if (//DH20[0-9]{2}Y([0-9]{1-2}) ) {
      if (OrdT) {
      }
      if (Tues) {
      }
    }
    */
  };

  var sd = $scope.sd;
  var homiliesByName = {};
  var homiliesArr = [];
  var homiliesByStringifiedDate = {};
  //$log.debug('$scope.classes: ');
  //$log.debug($scope.classes);
  for (var i=0; i < $scope.classes.length; i++) {
    var c = $scope.classes[i];
    //if ('date' in c) {
    if ('beluga' in c) {
      homiliesByStringifiedDate[c.date] = c;
      //$log.debug('c.date: ' + c.date);
    } else {
      //var regex = /([0-9]{4})-0?([1-9]{1,2}[0]?)-0?([1-9]{1,2}[0]?).*/
      var regex = /([0-9]{4})-([0-9]{2})-([0-9]{2}).*/
      var m = regex.exec(c['audio']);
      if (m != null) {
        //$log.debug('m[1]: ' + m[1]);
        //$log.debug('m[2]: ' + m[2]);
        //$log.debug('m[3]: ' + m[3]);
        //var origDateFormat = m[2] + '/' + m[3] + '/' + m[1];
        var origDateFormat = m[1] + '-' + m[2] + '-' + m[3];
        //$log.debug('origDateFormat: ' + origDateFormat);
        c.date = origDateFormat;
        homiliesByStringifiedDate[origDateFormat] = c;
      } else {
        var regex = /([0-9]{4})([0-9]{2})([0-9]{2}).*/
        var m = regex.exec(c['newAudio']);
        if (m != null) {
          var origDateFormat = m[1] + '-' + m[2] + '-' + m[3];
          //$log.debug('origDateFormat: ' + origDateFormat);
          c.date = origDateFormat;
          homiliesByStringifiedDate[origDateFormat] = c;
        } else {
          $log.debug('newAudio not matched: ' + c['newAudio']);
        }
      }
    }
    if ('liturgical_day' in c) {
      //$log.debug(c.liturgical_day);
      if (!(c.liturgical_day instanceof Array)) {
        c.liturgical_day = [c.liturgical_day];
        /*
      } else if (c.rssDate.substring(0,3) == 'Sun') {
        console.log('here3');
        console.log(c.liturgical_day[0]);
        //$log.debug(c.liturgical_day[0]);
        var ld = c.liturgical_day[0];
        for (var j=1; j < c.liturgical_day.length; j++) {
          ld = ld + ' / ' + c.liturgical_day[j];
        }
        c.liturgical_day = [ld];
        */
      }
      for (var j=0; j < c.liturgical_day.length; j++) {
        $scope.parseLiturgicalDay(homiliesByName, homiliesArr, c, j);
      }
    }
  }
  $log.debug('$scope.maxTagCount: ' + $scope.maxTagCount);
  $scope.allTagSizes = {};
  for (var tKey in $scope.allTags) {
    var count = $scope.allTags[tKey];
    var minFontSize = 80;
    var maxFactor = 12;
    var maxFontSize = 6 * minFontSize;
    var pctOfMax = count / $scope.maxTagCount;
    var size = maxFactor * minFontSize * pctOfMax;
    if (size < minFontSize) {
      size = minFontSize;
    }
    if (size > maxFontSize) {
      size = maxFontSize;
    }
    $log.debug('size: ' + size + ' count: ' + count + ' pctOfMax: ' + pctOfMax);
    $scope.allTagSizes[tKey] = size;
  }
  $log.debug('$scope.allTags:');
  $log.debug($scope.allTags);
  keysSorted = Object.keys($scope.allTags).sort(function(a, b) {
    return a.localeCompare(b);
  });
  var sortedTags = {};
  for (var i=0; i < keysSorted.length; i++) {
    sortedTags[keysSorted[i]] = $scope.allTags[keysSorted[i]];
  }
  $scope.allTags = sortedTags;
  $log.debug(keysSorted);
  homiliesArr;


  $scope.updateSearch = function() {
    $log.debug('updateSearch()');
    var matchingArr1 = [];
    var noText = true;
    if ($scope.searchText1.val != '') {
      matchingArr1 = $filter('filter')(homiliesArr, {'searchText': $scope.searchText1.val});
      $log.debug('matchingArr1.length: ' + matchingArr1.length);
      for (var i = 0; i < matchingArr1.length; i++) {
        $log.debug('matchingArr1['+i+']:');
        $log.debug(matchingArr1[i]);
      }
      noText = false;
    }
    var matchingArr2 = [];
    if ($scope.searchText2.val != '') {
      matchingArr2 = $filter('filter')(homiliesArr, {'searchText': $scope.searchText2.val});
      noText = false;
    }
    $scope.matchingArr = arrayUnique(matchingArr1.concat(matchingArr2));
    $scope.noResults = false;
    $scope.tooManyResults = false;
    if ($scope.matchingArr.length > 200 || noText) {
      $scope.tooManyResults = true;
    } else if ($scope.matchingArr.length == 0) {
      $scope.noResults = true;
    } else {
      if ($scope.matchingArr.length <= 2) {
        for (var i=0; i < $scope.matchingArr.length; i++) {
          if ($scope.c != null && $scope.c.id == $scope.matchingArr[i].id) {
            $scope.matchingArr.splice(i, 1);
          }
        }
      }
    }

    $log.debug('matchingArr');
    $log.debug($scope.matchingArr);
  }
  //$log.debug('homiliesByName: ');
  //$log.debug(homiliesByName);
  //$log.debug('homiliesByStringifiedDate: ');
  //$log.debug(homiliesByStringifiedDate);


  $scope.set2weeks = function(day) {
    $scope.monthStr = $filter('date')(day, 'MMMM');
    $scope.yearStr = day.getFullYear();
    $log.debug('$scope.yearStr: ' + $scope.yearStr);
    //$log.debug('set2weeks: ');
    //$log.debug(day);
    $scope.set2weeksday = day;
    var firstSundayOfFirstWeek = null;
    var firstDaySeen = false;
    $scope.firstOfMonth = null;
    while (true) {
      //$log.debug('day.getDay(): ' + day.getDay());
      if (day.getDate() == 1) {
        firstDaySeen = true;
        $scope.firstOfMonth = day;
      }
      if (day.getDay() == 0 && firstDaySeen) {
        //$log.debug('sundaysCounted: ' + sundaysCounted);
        firstSundayOfFirstWeek = day;
        break;
      }
      //day = new Date(day.UTC() - (24 * 60 * 60 * 1000));
      var previousDay = new Date(day.getTime());
      previousDay.setDate(day.getDate() - 1);
      day = previousDay;
    }

    //$log.debug('twoSundaysAgo: ' + twoSundaysAgo.toLocaleString());

    var weeks = [];
    var secondWeek = [];
    var day = firstSundayOfFirstWeek;
    //var years = [];
    var months = [];
    var monthDates = [];
    var fiveweeks = [];
    for (var i=0; i < 6; i++) {
      fiveweeks[i] = [];
      for (var j=0; j < 7; j++) {
        /*
        if (years.indexOf(day.getFullYear()) == -1) {
          //$log.debug("adding year: " + day.getFullYear());
          years.push(day.getFullYear());
        }
        */
        if (months.indexOf(day.getMonth()) == -1) {
          months.push(day.getMonth());
          monthDates.push(day);
        }
        var dayStr = $scope.getDayStr(day);
        //$log.debug('dayStr: ' + dayStr);
        fiveweeks[i][j] = {
          'cpObj': homiliesByStringifiedDate[dayStr],
          'dateStr' : dayStr,
          'dayStr' : day.getDate(),
          'dateObj' : day
        };
        var nextDay = new Date(day.getTime());
        nextDay.setDate(day.getDate() + 1);
        day = nextDay;
      }
    }
    $scope.fiveweeks = fiveweeks;

    /*
    if (years.length > 1) {
      $scope.yearStr = years[0] + ' / ' + years[1];
    } else {
      $scope.yearStr = years[0] + '';
    }
    //$log.debug('monthDates: ');
    //$log.debug(monthDates);
    if (monthDates.length > 1) {
      $scope.monthStr = $filter('date')(monthDates[0], 'MMMM') + 
        ' / ' + $filter('date')(monthDates[1], 'MMMM');
    } else {
      $scope.monthStr = $filter('date')(monthDates[0], 'MMMM');
    }
    */
  }

  $scope.getDayStr = function(day) {
    //var dayStr = (day.getMonth() + 1) + '/' + day.getDate() + '/' + day.getFullYear();
    var dayStr = day.getFullYear();
    dayStr += '-';
    if (day.getMonth() < 9) {
      dayStr += '0'
    }
    dayStr += day.getMonth() + 1;
    dayStr += '-';
    if (day.getDate() < 10) {
      dayStr += '0'
    }
    dayStr += day.getDate();

    //$log.debug('dayStr: ' + dayStr);
    return dayStr;
  }

  $scope.calWidgetChanged = function() {
    console.log($scope.monthStr);
    var newDt = new Date(Date.parse($scope.monthStr + '1, ' + $scope.yearStr));
    var dtStr = $filter('date')(new Date(newDt),'yyyy-MM-dd');
    console.log(dtStr);
    $scope.dt = newDt;
    $scope.set2weeks(newDt);
  }

  $scope.set2weeks($scope.dt);

  $scope.back = function() {
    var newDt = new Date($scope.firstOfMonth.getFullYear(), 
      $scope.firstOfMonth.getMonth(), 
      $scope.firstOfMonth.getDate());
    newDt.setMonth(newDt.getMonth() - 1);
    $scope.dt = newDt;
    $scope.set2weeks(newDt);
    var dtStr = $filter('date')(new Date(newDt),'yyyy-MM-dd');
    //$log.debug('dtStr: ' + dtStr);
    //$location.search('dt', dtStr);
    //$log.debug('back()');
  }

  $scope.forward = function() {
    var newDt = new Date($scope.firstOfMonth.getFullYear(), 
      $scope.firstOfMonth.getMonth(), 
      $scope.firstOfMonth.getDate());
    newDt.setMonth(newDt.getMonth() + 1);
    $scope.forward2(newDt);
  }

  $scope.forward2 = function(newDt) {
    $scope.dt = newDt;
    $scope.set2weeks(newDt);
    var dtStr = $filter('date')(new Date(newDt),'yyyy-MM-dd');
    //$log.debug('dtStr: ' + dtStr);
    //$location.search('dt', dtStr);
    //$log.debug('back()');
  }

  $scope.setMonthOnCal = function(d) {
    $log.debug('setMonthOnCal');
    $log.debug('d.date');
    $log.debug(d.date);
    var yearStr = d.date.substring(0,4);
    $log.debug('yearStr: ' + yearStr);
    var monthStr = d.date.substring(5,7);
    $log.debug('monthStr: ' + monthStr);
    var newDt = new Date(parseInt(yearStr),
      parseInt(monthStr) - 1,
      1);
    $log.debug('newDt: ');
    $log.debug(newDt);
    $scope.forward2(newDt);
  }

  $scope.showComments = function() {
    $scope.show_disqus = true;
  }

  $scope.showDayModalIsOpen = false;
  $scope.showDay = function(d) {
    $scope.showingAllTags = false;
    $scope.show_disqus = false;
    $log.debug('showDay(d): ');
    $log.debug(d);
    $scope.tagsfirstline = null;
    $scope.tagssubsequentlines = [];
    if (d == null) {
      $scope.c = null;
    }
    if (d != null && d.tags) {
      tags = d.tags.split(' ');
      if (tags != null && tags.length > 0) {
        $scope.tagsfirstline = tags[0];
        $scope.tagsfirstlinedisplay = tags[0].replace(new RegExp('_', 'g'), ' ');

        $scope.tagssubsequentlines = [];
        $scope.tagssubsequentlinesdisplay = [];
        for (var i=1; i < tags.length; i++) {
          $scope.tagssubsequentlines.push(tags[i]);
          $scope.tagssubsequentlinesdisplay.push(tags[i].replace(new RegExp('_', 'g'), ' '));
        }
      }
    }

    //d.litdaySelected = ld;
    $scope.showingDay = true;
    //$scope.day2show = d;
    if (d != null) {
      $scope.c = d;
      $log.debug('$scope.c.id: ' + $scope.c.id);
      //$location.path('/session').search({'course' : $scope.course, 'sessionId': c.id});
      $scope.sessionId = d.id;
      $log.debug('showDay.sessionId: ' + $scope.sessionId);
      //$location.search({'course' : $scope.course, 'sessionId': d.cpObj.id});
      //$scope.disqusConfig = $scope.assignDisqusParams($scope);
      $scope.assignDisqusParams($scope.sessionId);
      $log.debug('$scope.disqusConfig.disqus_shortname: '+ $scope.disqusConfig.disqus_shortname);

        //templateUrl: 'partials/course_specific/daily_modal.html',
      $location.search('showDay', d.date);
    }
    $scope.$watch('searchText1.val', function(newValue, oldValue) {
      $log.debug('searchText1 updated');
      if (oldValue != newValue) {
        $scope.updateSearch();
      }
    });
    $scope.$watch('searchText2.val', function(newValue, oldValue) {
      //$log.debug('searchText2 updated');
      if (oldValue != newValue) {
        $scope.updateSearch();
      }
    });
    if (!$scope.showDayModalIsOpen) {
      $scope.showDayModalIsOpen = true;
      $scope.searchRelated(d);
      $scope.modalInstance = $uibModal.open({
        animation: true,
        templateUrl: 'partials/course_specific/daily_session.html?cbp=20230723a704b04bbbedci',
        controller: ModalInstanceCtrl,
        size: 'lg',
        scope: $scope,
        preserveScope: true,
        bindToController: true
      });
      $scope.modalInstance.result.then(function (selectedItem) {
        $scope.selected = selectedItem;
      }, function () {
        $scope.showDayModalIsOpen = false;
        //$log.debug($scope.searchText1.val);
        //$log.info('Modal dismissed at: ' + new Date());
        $location.search('showDay', null);
      });
    }
    $scope.updateSearch();
    if (d != null) {
      $scope.setMonthOnCal(d);
    }
  }

  $scope.searchRelated = function(d) {
      $scope.searchText1 = { 'val': ''};
      $scope.searchText2 = { 'val': ''};
      if (d != null && d.hasOwnProperty('liturgical_day')) {
        for (var i=0; i < d.liturgical_day.length; i++) {
          if (i == 0) {
            $scope.searchText1.val = d.liturgical_day[i];
          } else {
            $scope.searchText2.val = d.liturgical_day[i];
          }
        }
      }
      $scope.updateSearch();
  }

  $scope.toggleShowAllTags = function() {
    $log.debug('toggleShowAllTags: ' + $scope.showingAllTags);
    $scope.showingAllTags = !$scope.showingAllTags;
  }

  if ($location.search().showDay) {
    //$log.debug('homiliesByStringifiedDate[$location.search().showDay]: ');
    //$log.debug(homiliesByStringifiedDate[$location.search().showDay]);
    $scope.showDay(homiliesByStringifiedDate[$location.search().showDay]);
  }

  $scope.ok = function () {
    $log.debug('ok');
    $scope.modalInstance.dismiss();
    $location.search('showDay', null);
  };

  $scope.cancel = function () {
    //$log.debug('cancel');
    $uibModal.dismiss('cancel');
    $location.search('showDay', null);
  };

});

var ModalInstanceCtrl =  function ($scope, $controller, $window, $http, $log, $location) {

//cpApp.controller('ModalInstanceCtrl', function ($scope, $uibModalInstance, parentScope) {
//cpApp.controller('ModalInstanceCtrl', function ($scope, $uibModalInstance) {

}
