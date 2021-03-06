//angular.module('cpApp', ['ngRoute', 'ngDisqus'] //, function($compileProvider) {
  //}
angular.module('cpApp', ['ngRoute', 'ngSanitize', 'angularUtils.directives.dirDisqus', 'ngAnimate', 'ui.bootstrap'])
  .config(function($routeProvider, $compileProvider, $locationProvider ) {
  //.config(function($routeProvider, $compileProvider, $locationProvider, $disqusProvider ) {
    $compileProvider.aHrefSanitizationWhitelist(/^\s*(https?|ftp|mailto|file|itms):/);
    $routeProvider
      .when('/', {
        reloadOnSearch: false,
        controller:'MainController',
        templateUrl:'web/main.html?cbp=20160429'
      })
      .when('/class', {
        reloadOnSearch: true,
        controller:'ClassController',
        templateUrl:'web/classContent.html?cbp=20160429'
      })
      .when('/session', {
        reloadOnSearch: true,
        controller:'SessionController',
        templateUrl:'web/session.html?cbp=20160429'
      })
      .otherwise({
        redirectTo:'/'
      });
    /*
    $locationProvider.html5Mode({
      enabled: true
    });
    */
    $locationProvider.html5Mode(true);
    $locationProvider.hashPrefix('!');
    //$disqusProvider.setShortname('catholicpatrimony');
  })
  .controller('MenuController', function($scope, $location, $routeParams, $log, $sce) {
    //$log.debug('defining trustSrc');
    $scope.trustSrc = function(src) {
      try {
        //$log.debug('trustSrc: ' + src);
        return $sce.trustAsResourceUrl(src);
      } catch (e) {
      }
    }
    $scope.gdoc_loaded = function() {
      var f = function(id)
      {
          document.getElementById(id).style.display = "none";
      };
      f("header");
      f("footer");
    };
    $scope.cp = cp;
    $scope.uncovering_2015_schedule = uncovering_2015_schedule;
    $scope.dropDownMenu = [];
    $scope.topLevelMenu = [];
    for (var i=0; i < cp.length; i++) {
      $scope.cp[i].idx = i;
      if (cp[i].seriesData.separate_menu && cp[i].seriesData.separate_menu == "TRUE") {
        $scope.topLevelMenu.push(cp[i]);
      } else if (cp[i].seriesData.publish && cp[i].seriesData.publish == "FALSE") {
      } else {
        $scope.dropDownMenu.push(cp[i]);
      }
      if (cp[i].seriesData.include_zips && cp[i].seriesData.include_zips == "FALSE") {
        //$log.debug('include_zips = false');
        cp[i].seriesData.includeZips = false;
      } else {
        //$log.debug('include_zips = true');
        cp[i].seriesData.includeZips = true;
      }
    }
    $scope.dropDownClicked = function(course) {
      setClass($scope, "dropDown");
      $location.path('/class').search({'course' : course});
    }
    $scope.topLevelClassClicked = function(course) {
      setClass($scope, "topLevelClass");
      $location.path('/class').search({'course' : course});
    }
    $scope.aboutClicked = function(course) {
      setClass($scope, "about");
      //$location.path('');
    }
    $log.debug(cp);
  })
  //.controller('MainController', function($scope, $location, $routeParams, $log) {
  .controller('ClassController', function($scope, $location, $routeParams, $log, $modal) {
    /*
    if (!$scope['loadingModal']) {
      $scope.loadingModal = {val: null};
    }
    $scope.$on('$includeContentRequested', function (event, data) {
      $log.debug('includeContentRequested'); 
      try {
        $scope.loadingModal.val = $modal.open({
          templateUrl: 'web/loading.html',
          controller: 'ModalController',
          backdrop : 'static',
          keyboard: false,
          size: 'sm'
        });
      } catch (e) {
        $log.debug(e);
      }
    });
    */
      /*
      */
    //$log.debug('in ClassController');
    $scope.cp = cp;
    //$log.debug($routeParams);
    if ($routeParams['course'] != null) {
      //$log.debug('found course');
      selectClass($scope, $routeParams.course);
    }
    if ($routeParams['enableComments'] != null) {
      $scope.enableComments = true;
    } else {
      $scope.enableComments = false;
    }
    //$log.debug('enableComments: ' + $scope.enableComments);

    $scope.sessionClicked = function(c) {
      $scope.c = c;
      $location.path('/session').search({'course' : $scope.course, 'sessionId': c.id});
    }
  })
  .controller('SessionController', function($scope, $location, $routeParams, $log, $sce) {
    $scope.myDisqus_contentLoaded = false;
    //$log.debug('in SessionController');
    $scope.cp = cp;
    $log.debug($routeParams);
    /*
    if ($routeParams['course'] != null) {
      $scope.session = 
    }
    */
    if ($routeParams['course'] != null) {
      $log.debug('found course');
      selectClass($scope, $routeParams.course);
      if ($routeParams['sessionId'] != null) {
        for (var i=0; i < $scope.classes.length; i++) {
          if ($scope.classes[i].id == $routeParams['sessionId']) {
            $scope.c = $scope.classes[i];
          }
        }
        $scope.disqusConfig = {
          disqus_shortname: $scope.c.title,
          disqus_identifier: 'cp.com.session_' + $routeParams['course'] + '_' + $routeParams['sessionId'],
          disqus_url: $location.absUrl();
        };
        $scope.myDisqus_identifier = 'cp.com.session_' + $routeParams['course'] + '_' + $routeParams['sessionId'];
        $scope.myDisqus_title = $scope.c.title;
        $scope.myDisqus_url = $location.absUrl();
        $log.debug($scope.myDisqus_identifier);
        $log.debug('d1');
        $log.debug($scope.myDisqus_title);
        document.title = $scope.myDisqus_title
        $log.debug('d2');
        $log.debug($scope.myDisqus_url);
        $log.debug('d3');
        $scope.myDisqus_contentLoaded = true;
      }
    }
  }).controller('ModalController', function($scope, $location, $routeParams, $http) {
  })

var selectClass = function(scope, course) {
  /*
  $log.debug(idx);
  $log.debug(scope.cp[idx]);
  */
  scope.course = course;
  for (var i=0; i < cp.length; i++) {
    if (cp[i].seriesData.normalized_name == course) {
      scope.seriesSelected = cp[i];
    }
  }
  scope.sd = scope.seriesSelected.seriesData;
  scope.classes = scope.seriesSelected.classes;
  /* the reason I'm doing this here is because firefox is line breaking the
   * straight template solution (which I left commented out in classContent.html */
  for (var i=0; i < scope.classes.length; i++) {
    var fileicons = [];
    var c = scope.classes[i];
    c.fileicons = fileicons;
    if ('new_handout_file' in c) {
      for (var j=0; j < c.new_handout_file.length; j++) {
        var nhf = c.new_handout_file[j];
        if (nhf.indexOf('.pdf') > -1) {
          fileicons[j] = 'pdficon.gif';
        } else if (nhf.indexOf('.doc') > -1) {
          fileicons[j] = 'docicon.png';
        } else if (nhf.indexOf('.ppt') > -1) {
          fileicons[j] = 'document_powerpoint.png';
        } else if (nhf.indexOf('http') > -1) {
          fileicons[j] = 'Link_symbol_16.png';
        }
      }
    }
  }
}

var setClass = function(scope, tlm) {
  scope.aboutClass="";
  scope.dropDownClass="";
  scope.topLevelClass="";
  if (tlm == "about") {
    scope.aboutClass="active";
  } else if (tlm == "dropDown") {
    scope.dropDownClass="active";
  } else if (tlm == "topLevelClass") {
    scope.topLevelClass="active";
  }

  /*
  $log.debug("scope.aboutClass: " + scope.aboutClass  );
  $log.debug("scope.dropDownClass: "+   scope.dropDownClass  );
  $log.debug("scope.topLevelClass: "+  scope.topLevelClass  );
  */
}


